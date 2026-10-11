from fastapi import APIRouter, HTTPException

from app.db import pool
from app.models.api import SourceDetail
from app.routers.collections import SOURCE_COLUMNS
from app.services.links import deep_link

router = APIRouter(tags=["sources"])


@router.get("/sources/{source_id}", response_model=SourceDetail)
def get_source(source_id: int):
    with pool().connection() as conn:
        src = conn.execute(f"SELECT {SOURCE_COLUMNS}, s.ext_id, s.media_url, s.overview FROM sources s WHERE s.id = %s",
                           (source_id,)).fetchone()
        if not src:
            raise HTTPException(404, "Not found")
        ready = src["status"] == "ready"
        segs = conn.execute(
            "SELECT id, ord, start_s, end_s, anchor, text, summary, tags FROM segments WHERE source_id = %s ORDER BY ord",
            (source_id,)).fetchall() if ready else []
        chapters = conn.execute(
            "SELECT id, start_s, end_s, title, summary FROM chapters WHERE source_id = %s ORDER BY ord",
            (source_id,)).fetchall() if ready else []
        quotes = conn.execute(
            """SELECT q.id, q.segment_id, q.ts_s, q.quote, q.is_advice, seg.text, seg.anchor
               FROM key_quotes q JOIN segments seg ON seg.id = q.segment_id
               WHERE q.source_id = %s ORDER BY q.ts_s""", (source_id,)).fetchall() if ready else []
    for s in segs:
        s["deep_link"] = deep_link(src, s["start_s"], s["text"], s["anchor"])
    for q in quotes:
        q["deep_link"] = deep_link(src, q["ts_s"], q.pop("text"), q.pop("anchor"))
    return {**src, "chapters": chapters, "segments": segs, "key_quotes": quotes,
            "overview": src["overview"] if ready else None}
