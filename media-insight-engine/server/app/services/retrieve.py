"""Hybrid retrieval: vector search + Postgres full text, merged by reciprocal-rank fusion (FR-4.1)."""
import re

from app.db import pool
from app.services import embed

CANDIDATES = 30
RRF_K = 60


def _filters(collection: str, f: dict) -> tuple[str, dict]:
    where = ["s.status = 'ready'", "NOT s.archived"]
    params: dict = {}
    if collection != "all":  # FR-1.6: collections are isolated unless the user picks "all"
        where.append("s.collection_id = %(collection)s")
        params["collection"] = collection
    if f.get("source_ids"):
        where.append("s.id = ANY(%(source_ids)s)")
        params["source_ids"] = list(f["source_ids"])
    if f.get("tags"):
        where.append("seg.tags && %(tags)s::text[]")
        params["tags"] = list(f["tags"])
    if f.get("date_from"):
        where.append("s.published_at >= %(date_from)s")
        params["date_from"] = f["date_from"]
    if f.get("date_to"):
        where.append("s.published_at <= %(date_to)s")
        params["date_to"] = f["date_to"]
    return " AND ".join(where), params


def or_query(text: str) -> str:
    """'is the SAT required?' → 'is | the | sat | required' (OR, so a long question still matches)."""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text) if len(w) > 1]
    return " | ".join(dict.fromkeys(words))


def rrf(*ranked_lists: list[int]) -> list[int]:
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, seg_id in enumerate(ranked):
            scores[seg_id] = scores.get(seg_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(scores, key=lambda i: -scores[i])


def retrieve(collection: str, query: str, filters: dict | None = None, k: int = 10) -> list[dict]:
    where, params = _filters(collection, filters or {})
    base = f"FROM segments seg JOIN sources s ON s.id = seg.source_id WHERE {where}"
    with pool().connection() as conn, conn.transaction():
        conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")  # keep results when filters are tight
        vec = [r["id"] for r in conn.execute(
            f"SELECT seg.id {base} AND seg.embedding IS NOT NULL ORDER BY seg.embedding <=> %(qv)s LIMIT {CANDIDATES}",
            {**params, "qv": embed.query(query)})]
        txt = []
        if (tsq := or_query(query)):
            txt = [r["id"] for r in conn.execute(
                f"""SELECT seg.id {base} AND seg.tsv @@ to_tsquery('english', %(tsq)s)
                    ORDER BY ts_rank_cd(seg.tsv, to_tsquery('english', %(tsq)s)) DESC LIMIT {CANDIDATES}""",
                {**params, "tsq": tsq})]
        top = rrf(vec, txt)[:k]
        if not top:
            return []
        rows = conn.execute(
            """SELECT seg.id AS segment_id, seg.start_s, seg.end_s, seg.anchor, seg.text, seg.summary, seg.tags,
                      s.id AS source_id, s.collection_id, s.type, s.url, s.ext_id, s.media_url, s.host, s.published_at,
                      coalesce(s.title, s.label, s.url) AS source_title
               FROM segments seg JOIN sources s ON s.id = seg.source_id WHERE seg.id = ANY(%s)""",
            (top,)).fetchall()
    by_id = {r["segment_id"]: r for r in rows}
    return [by_id[i] for i in top if i in by_id]
