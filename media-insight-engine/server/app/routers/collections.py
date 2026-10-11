from fastapi import APIRouter, HTTPException, Query

from app.config import ConfigError, collection_slugs, load_collection
from app.db import pool
from app.models.api import Collection, SourceSummary, SyncLog
from app.services.sync import SyncBusy, sync_collection

router = APIRouter(tags=["collections"])

SOURCE_COLUMNS = """s.id, s.collection_id, s.type, s.url, s.label, s.priority, s.title, s.host, s.published_at,
    s.duration_s, s.status, s.error, s.archived, s.ingested_at, s.progress, s.feed_url,
    (SELECT count(*) FROM segments seg WHERE seg.source_id = s.id) AS segment_count,
    (s.published_at IS NULL OR s.published_at <= current_date - (SELECT make_interval(months => c.stale_after_months)
                                                                  FROM collections c WHERE c.id = s.collection_id)) AS stale"""


def require_collection(collection_id: str) -> None:
    if collection_id not in collection_slugs():
        raise HTTPException(404, f"Collection '{collection_id}' not found")


@router.get("/collections", response_model=list[Collection])
def list_collections():
    with pool().connection() as conn:
        rows = {r["id"]: r for r in conn.execute("SELECT * FROM collections")}
        counts = {r["collection_id"]: r for r in conn.execute(
            """SELECT collection_id,
                 count(*) FILTER (WHERE NOT archived) AS total,
                 count(*) FILTER (WHERE NOT archived AND status = 'ready') AS ready,
                 count(*) FILTER (WHERE NOT archived AND status IN ('queued','transcribing','analyzing')) AS in_progress,
                 count(*) FILTER (WHERE NOT archived AND status = 'failed') AS failed,
                 count(*) FILTER (WHERE archived) AS archived
               FROM sources GROUP BY collection_id""")}
    out = []
    for slug in collection_slugs():
        row = rows.get(slug)
        try:  # the file is the source of truth; fall back to the last synced row if it's broken right now
            col = load_collection(slug)
            info = dict(name=col.name, lens_name=col.lens_name, lens_tags=col.lens.tags,
                        focus_note=col.focus_note, segment_seconds=col.lens.segment_seconds)
        except ConfigError:
            info = dict(name=row["name"] if row else slug, lens_name=row["lens_name"] if row else "invalid",
                        lens_tags=row["lens_tags"] if row else [], focus_note=row["focus_note"] if row else None,
                        segment_seconds=row["segment_seconds"] if row else 60)
        c = counts.get(slug) or {"total": 0, "ready": 0, "in_progress": 0, "failed": 0, "archived": 0}
        out.append({"id": slug, **info, "last_synced_at": row["last_synced_at"] if row else None,
                    "source_counts": {k: c[k] for k in ("total", "ready", "in_progress", "failed", "archived")}})
    return sorted(out, key=lambda c: c["name"].lower())


@router.post("/sync", response_model=SyncLog)
def sync(collection: str = Query(pattern=r"^[a-z0-9-]+$")):
    try:
        return sync_collection(collection)
    except FileNotFoundError:
        raise HTTPException(404, f"Collection '{collection}' not found (no config/collections/{collection}.yaml)")
    except ConfigError as e:
        raise HTTPException(422, str(e))
    except SyncBusy:
        raise HTTPException(409, f"Sync already running for '{collection}'")


@router.get("/collections/{collection_id}/sync-log", response_model=SyncLog)
def latest_sync_log(collection_id: str):
    require_collection(collection_id)
    with pool().connection() as conn:
        row = conn.execute("SELECT * FROM sync_logs WHERE collection_id = %s ORDER BY id DESC LIMIT 1",
                           (collection_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Collection '{collection_id}' has not been synced yet")
    return row


@router.get("/collections/{collection_id}/sources", response_model=list[SourceSummary], tags=["sources"])
def list_sources(collection_id: str, include_archived: bool = False):
    require_collection(collection_id)
    with pool().connection() as conn:
        return conn.execute(
            f"""SELECT {SOURCE_COLUMNS} FROM sources s
                WHERE s.collection_id = %s AND (%s OR NOT s.archived)
                ORDER BY CASE s.priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                         lower(coalesce(s.label, s.title, s.url))""",
            (collection_id, include_archived)).fetchall()
