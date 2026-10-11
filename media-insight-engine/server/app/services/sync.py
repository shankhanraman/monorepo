"""Sync a collection's YAML file with the database (FR-1.3, FR-1.4). Idempotent; never deletes."""
import threading
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from app.config import Collection, InvalidEntry, SourceEntry, load_collection
from app.db import pool
from app.services import jobs
from app.services.urls import detect_type, normalize, youtube_id

DAY2_TYPES = {"audio", "pdf"}
IN_PROGRESS = {"queued", "transcribing", "analyzing"}


class SyncBusy(Exception):
    pass


@dataclass
class Step:
    url: str
    label: str | None
    action: str              # queued | skipped | failed | archived (what the log shows)
    reason: str
    op: str                  # insert | requeue | archive | refresh | none (what to do in the DB)
    source_id: int | None = None
    entry: SourceEntry | None = None
    type: str | None = None
    ext_id: str | None = None
    unarchive: bool = False


def plan_sync(col: Collection, existing: dict[str, dict]) -> list[Step]:
    """Decide what happens to every URL. `existing` maps normalized url → {id, status, archived, error}."""
    steps: list[Step] = []
    seen: dict[str, int] = {}
    for n, entry in enumerate(col.entries, start=1):
        if isinstance(entry, InvalidEntry):
            steps.append(Step(entry.url or "(no url)", None, "failed", entry.reason, "none"))
            continue
        try:
            url = normalize(entry.url)
        except ValueError as e:
            steps.append(Step(entry.url, entry.label, "failed", f"Invalid URL: {e}", "none"))
            continue
        if url in seen:
            steps.append(Step(url, entry.label, "failed", f"Duplicate of entry {seen[url]} in the file", "none"))
            continue
        seen[url] = n
        kind = entry.type or detect_type(url)
        if kind in DAY2_TYPES:
            steps.append(Step(url, entry.label, "failed", f"Type '{kind}' is not supported until Day 2", "none"))
            continue
        ext_id = youtube_id(url)
        if kind == "youtube" and not ext_id:
            steps.append(Step(url, entry.label, "failed", "Not a YouTube video URL", "none"))
            continue
        common = dict(entry=entry, type=kind, ext_id=ext_id)
        row = existing.get(url)
        if row is None:
            steps.append(Step(url, entry.label, "queued", "New URL", "insert", **common))
            continue
        restored = "Restored, " if row["archived"] else ""
        if row["status"] == "ready":
            steps.append(Step(url, entry.label, "skipped", f"{restored}Already ready", "refresh",
                              row["id"], unarchive=row["archived"], **common))
        elif row["status"] in IN_PROGRESS:
            steps.append(Step(url, entry.label, "skipped", f"{restored}Already being ingested ({row['status']})",
                              "refresh", row["id"], unarchive=row["archived"], **common))
        else:  # failed → retry
            last = f" (last error: {row['error']})" if row.get("error") else ""
            steps.append(Step(url, entry.label, "queued", f"{restored}Retrying{last}", "requeue",
                              row["id"], unarchive=row["archived"], **common))
    for url, row in existing.items():
        if url not in seen and not row["archived"]:
            steps.append(Step(url, None, "archived", f"Removed from {col.id}.yaml", "archive", row["id"]))
    return steps


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def sync_collection(slug: str) -> dict:
    """Raises FileNotFoundError, ConfigError or SyncBusy."""
    col = load_collection(slug)
    with _locks_guard:
        lock = _locks.setdefault(slug, threading.Lock())
    if not lock.acquire(blocking=False):
        raise SyncBusy(slug)
    try:
        return _apply(col)
    finally:
        lock.release()


def upsert_collection(conn, col: Collection, synced: bool = True) -> None:
    conn.execute(
        """INSERT INTO collections (id, name, lens_name, lens_text, lens_tags, focus_note,
                                    segment_seconds, stale_after_months, last_synced_at)
           VALUES (%(id)s, %(name)s, %(lens_name)s, %(lens_text)s, %(tags)s, %(focus)s, %(secs)s, %(stale)s,
                   CASE WHEN %(synced)s THEN now() END)
           ON CONFLICT (id) DO UPDATE SET name = excluded.name, lens_name = excluded.lens_name,
             lens_text = excluded.lens_text, lens_tags = excluded.lens_tags,
             focus_note = excluded.focus_note, segment_seconds = excluded.segment_seconds,
             stale_after_months = excluded.stale_after_months,
             last_synced_at = CASE WHEN %(synced)s THEN now() ELSE collections.last_synced_at END""",
        {"id": col.id, "name": col.name, "lens_name": col.lens_name, "lens_text": col.lens_text,
         "tags": col.lens.tags, "focus": col.focus_note, "secs": col.lens.segment_seconds,
         "stale": col.lens.stale_after_months, "synced": synced})


def _apply(col: Collection) -> dict:
    with pool().connection() as conn, conn.transaction():
        upsert_collection(conn, col)
        rows = conn.execute("SELECT id, url, status, archived, error FROM sources WHERE collection_id = %s",
                            (col.id,)).fetchall()
        steps = plan_sync(col, {r["url"]: r for r in rows})
        for s in steps:
            e = s.entry
            if s.op == "insert":
                s.source_id = conn.execute(
                    """INSERT INTO sources (collection_id, type, url, ext_id, label, priority, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (col.id, s.type, s.url, s.ext_id, e.label, e.priority, e.notes)).fetchone()["id"]
            elif s.op in ("refresh", "requeue"):
                conn.execute(
                    """UPDATE sources SET label = %s, priority = %s, notes = %s, archived = false,
                         status = CASE WHEN %s THEN 'queued' ELSE status END,
                         error = CASE WHEN %s THEN NULL ELSE error END, updated_at = now()
                       WHERE id = %s""",
                    (e.label, e.priority, e.notes, s.op == "requeue", s.op == "requeue", s.source_id))
            elif s.op == "archive":
                conn.execute("UPDATE sources SET archived = true, updated_at = now() WHERE id = %s", (s.source_id,))
        entries = [{"url": s.url, "label": s.label, "action": s.action, "reason": s.reason,
                    "source_id": s.source_id} for s in steps]
        summary = {a: sum(1 for s in steps if s.action == a) for a in ("queued", "skipped", "failed", "archived")}
        log = conn.execute(
            "INSERT INTO sync_logs (collection_id, summary, entries) VALUES (%s, %s, %s) RETURNING id, created_at",
            (col.id, Jsonb(summary), Jsonb(entries))).fetchone()
    for s in steps:  # after commit, so workers see the rows
        if s.action == "queued":
            jobs.submit_ingest(s.source_id)
    return {"id": log["id"], "collection_id": col.id, "created_at": log["created_at"],
            "summary": summary, "entries": entries}
