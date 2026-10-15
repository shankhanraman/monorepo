"""Sync a collection's YAML file with the database (FR-1.3, FR-1.4). Idempotent; never deletes."""
import logging
import threading
from dataclasses import dataclass
from datetime import date

from psycopg.types.json import Jsonb

from app.config import Collection, InvalidEntry, SourceEntry, load_collection
from app.db import pool
from app.services import feeds as feedlib, jobs
from app.services.urls import detect_type, normalize, youtube_id

log = logging.getLogger("sync")
IN_PROGRESS = {"queued", "transcribing", "analyzing"}


class SyncBusy(Exception):
    pass


@dataclass
class Step:
    url: str
    label: str | None
    action: str              # queued | skipped | failed | archived | feed (what the log shows)
    reason: str
    op: str                  # insert | requeue | archive | refresh | none (what to do in the DB)
    source_id: int | None = None
    entry: SourceEntry | None = None
    type: str | None = None
    ext_id: str | None = None
    feed_url: str | None = None
    # known up front for feed episodes (title/date/duration come from the feed)
    title: str | None = None
    published_at: date | None = None
    duration_s: int | None = None
    media_url: str | None = None


def _decide(url: str, label: str | None, row: dict | None, new_reason: str, **common) -> Step:
    """New → insert; ready / in progress → skip; failed → retry. Archived rows that are listed again come back."""
    if row is None:
        return Step(url, label, "queued", new_reason, "insert", **common)
    restored = "Restored, " if row["archived"] else ""
    if row["status"] == "ready":
        return Step(url, label, "skipped", f"{restored}Already ready", "refresh", row["id"], **common)
    if row["status"] in IN_PROGRESS:
        return Step(url, label, "skipped", f"{restored}Already being ingested ({row['status']})", "refresh",
                    row["id"], **common)
    last = f" (last error: {row['error']})" if row.get("error") else ""
    return Step(url, label, "queued", f"{restored}Retrying{last}", "requeue", row["id"], **common)


def plan_sync(col: Collection, existing: dict[str, dict], feeds: dict[str, "feedlib.Feed | str"] | None = None) -> list[Step]:
    """Decide what happens to every URL. Pure: feeds are fetched by the caller.

    existing: normalized url → {id, status, archived, error, feed_url}
    feeds:    normalized feed url → parsed Feed, or the error text if it couldn't be read
    """
    feeds = feeds or {}
    steps: list[Step] = []
    seen: dict[str, int] = {}
    listed_feeds: set[str] = set()
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
        if kind == "spotify":
            steps.append(Step(url, entry.label, "failed",
                              "Spotify audio is DRM-protected: use the show's RSS feed instead", "none"))
            continue
        if kind == "rss":
            listed_feeds.add(url)  # its episodes stay, even if the feed can't be read this time
            steps += _feed_steps(url, entry, feeds.get(url), existing, seen, n)
            continue
        ext_id = youtube_id(url)
        if kind == "youtube" and not ext_id:
            steps.append(Step(url, entry.label, "failed", "Not a YouTube video URL", "none"))
            continue
        steps.append(_decide(url, entry.label, existing.get(url), "New URL", entry=entry, type=kind, ext_id=ext_id))
    for url, row in existing.items():
        if url not in seen and not row["archived"] and row.get("feed_url") not in listed_feeds:
            steps.append(Step(url, None, "archived", f"Removed from {col.id}.yaml", "archive", row["id"]))
    return steps


def _feed_steps(url: str, entry: SourceEntry, feed, existing: dict, seen: dict, n: int) -> list[Step]:
    if not isinstance(feed, feedlib.Feed):
        return [Step(url, entry.label, "failed", f"Could not read feed: {feed or 'not fetched'}", "none")]
    if not feed.episodes:
        return [Step(url, entry.label or feed.title, "failed", "Feed has no episodes with audio", "none")]
    chosen = feedlib.select(feed, entry.episodes, entry.match)
    how = f"latest {entry.episodes}" + (f" matching '{entry.match}'" if entry.match else "")
    steps = [Step(url, entry.label or feed.title, "feed",
                  f"Feed read: {len(chosen)} of {len(feed.episodes)} episodes selected ({how})", "none")]
    for ep in chosen:
        try:
            ep_url = normalize(ep.url)
        except ValueError:
            steps.append(Step(ep.url, ep.title, "failed", "Episode has an invalid audio URL", "none", feed_url=url))
            continue
        if ep_url in seen:
            steps.append(Step(ep_url, ep.title, "failed", f"Duplicate of entry {seen[ep_url]} in the file", "none",
                              feed_url=url))
            continue
        seen[ep_url] = n
        steps.append(_decide(ep_url, ep.title, existing.get(ep_url), "New episode", entry=entry, type="audio",
                             feed_url=url, title=ep.title, published_at=ep.published_at,
                             duration_s=ep.duration_s, media_url=ep.url))
    return steps


def fetch_feeds(col: Collection) -> dict[str, "feedlib.Feed | str"]:
    """Network part of a sync, done before the database transaction."""
    out: dict[str, feedlib.Feed | str] = {}
    for entry in col.entries:
        if isinstance(entry, InvalidEntry):
            continue
        try:
            url = normalize(entry.url)
        except ValueError:
            continue
        if (entry.type or detect_type(url)) == "rss" and url not in out:
            try:
                out[url] = feedlib.fetch(entry.url)
            except feedlib.FeedError as e:
                log.warning("feed %s: %s", entry.url, e)
                out[url] = str(e)
    return out


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
        return _apply(col, fetch_feeds(col))
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


def _apply(col: Collection, feeds: dict) -> dict:
    with pool().connection() as conn, conn.transaction():
        upsert_collection(conn, col)
        rows = conn.execute("SELECT id, url, status, archived, error, feed_url FROM sources WHERE collection_id = %s",
                            (col.id,)).fetchall()
        steps = plan_sync(col, {r["url"]: r for r in rows}, feeds)
        for s in steps:
            e = s.entry
            if s.op == "insert":
                s.source_id = conn.execute(
                    """INSERT INTO sources (collection_id, type, url, ext_id, label, priority, notes,
                                            feed_url, title, published_at, duration_s, media_url)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (col.id, s.type, s.url, s.ext_id, s.label, e.priority, e.notes,
                     s.feed_url, s.title, s.published_at, s.duration_s, s.media_url)).fetchone()["id"]
            elif s.op in ("refresh", "requeue"):
                conn.execute(
                    """UPDATE sources SET label = %s, priority = %s, notes = %s, archived = false,
                         status = CASE WHEN %s THEN 'queued' ELSE status END,
                         error = CASE WHEN %s THEN NULL ELSE error END, updated_at = now()
                       WHERE id = %s""",
                    (s.label, e.priority, e.notes, s.op == "requeue", s.op == "requeue", s.source_id))
            elif s.op == "archive":
                conn.execute("UPDATE sources SET archived = true, updated_at = now() WHERE id = %s", (s.source_id,))
        entries = [{"url": s.url, "label": s.label, "action": s.action, "reason": s.reason,
                    "source_id": s.source_id, "feed_url": s.feed_url} for s in steps]
        summary = {a: sum(1 for s in steps if s.action == a) for a in ("queued", "skipped", "failed", "archived")}
        log_row = conn.execute(
            "INSERT INTO sync_logs (collection_id, summary, entries) VALUES (%s, %s, %s) RETURNING id, created_at",
            (col.id, Jsonb(summary), Jsonb(entries))).fetchone()
    queued_any = False
    for s in steps:  # after commit, so workers see the rows
        if s.action == "queued":
            queued_any = True
            jobs.submit_ingest(s.source_id, s.type)
    if not queued_any:
        # Nothing to ingest, so no drain will fire: refresh the collection-wide insights now
        # (e.g. a re-sync where every source is already ready, or only metadata changed).
        jobs.submit_synthesis(col.id)
    return {"id": log_row["id"], "collection_id": col.id, "created_at": log_row["created_at"],
            "summary": summary, "entries": entries}
