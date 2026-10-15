"""Collection-wide synthesis across all ready sources — the analytical agent behind the home page.

The quantitative Atlas (coverage, timeline, consensus) is computed here in Python so it stays
trustworthy; the model only writes the qualitative insight cards, which are then checked against
the real sources. Runs in the background after a sync drains (see jobs.submit_synthesis)."""
import logging
import re
from datetime import date
from typing import Literal

import anthropic
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from app.config import ConfigError, load_collection, settings
from app.db import pool
from app.services import llm
from app.services.llm import ModelRefusal, ModelUnavailable, api_error_message

log = logging.getLogger("insights")

KINDS = ("theme", "contradiction", "trend", "gap")
MAX_CHAPTERS = 8   # per source, in the digest
MAX_QUOTES = 4


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


class EvidenceOut(BaseModel):
    source_id: int
    quote: str
    role: Literal["supports", "opposes", "context"] = "supports"


class InsightOut(BaseModel):
    kind: Literal["theme", "contradiction", "trend", "gap"]
    title: str
    detail: str
    tag: str | None = None
    source_ids: list[int] = []
    evidence: list[EvidenceOut] = []
    confidence: Literal["high", "medium", "low"] = "medium"
    recommended_action: str | None = None


class InsightsOut(BaseModel):
    insights: list[InsightOut]


# ---- pure functions (no DB / no model); unit-tested in tests/test_insights.py ----

def coverage(lens_tags: list[str], source_tag_sets: list[set[str]]) -> list[dict]:
    """Per Lens tag, how many ready sources carry it. A tag with 0–1 sources is a gap."""
    rows = []
    for tag in lens_tags:
        tl = tag.lower()
        n = sum(1 for tags in source_tag_sets if tl in {t.lower() for t in tags})
        rows.append({"tag": tag, "sources": n, "gap": n <= 1})
    rows.sort(key=lambda r: (-r["sources"], r["tag"].lower()))
    return rows


def timeline(dates: list[date | None]) -> list[dict]:
    """Ready sources grouped by publish year, with undated ones in a trailing bucket."""
    years: dict[int, int] = {}
    undated = 0
    for d in dates:
        if d is None:
            undated += 1
        else:
            years[d.year] = years.get(d.year, 0) + 1
    out = [{"period": str(y), "sources": years[y]} for y in sorted(years)]
    if undated:
        out.append({"period": "Undated", "sources": undated})
    return out


def consensus(insights: list[dict]) -> int | None:
    """Agreement among findings: themes / (themes + contradictions).

    None when there is nothing to measure (no themes and no contradictions) — the UI shows '—'
    rather than a fabricated 100% on a thin or trend-only collection.
    """
    themes = sum(1 for i in insights if i["kind"] == "theme")
    contras = sum(1 for i in insights if i["kind"] == "contradiction")
    denom = themes + contras
    return None if denom == 0 else round(100 * themes / denom)


# Counselor action-value order: conflicting guidance first, then gaps, trends, consensus.
_PRIORITY = {"contradiction": 0, "gap": 1, "trend": 2, "theme": 3}


def prioritize(insights: list[dict]) -> list[dict]:
    """Deterministic order so the highest-signal cards lead (ties: more supporting sources first)."""
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(insights, key=lambda i: (_PRIORITY.get(i["kind"], 9),
                                           confidence_rank.get(i.get("confidence", "medium"), 1),
                                           -len(i["sources"])))


def check(out: InsightsOut, source_map: dict[int, dict], lens_tags: list[str]) -> list[dict]:
    """Keep only insights the real sources support: ids must be ready, tags from the Lens vocabulary."""
    allowed = {t.lower(): t for t in lens_tags}
    ready = set(source_map)
    result = []
    for ins in out.insights:
        if ins.kind not in KINDS:
            continue
        ids = [i for i in dict.fromkeys(ins.source_ids) if i in ready]
        if ins.kind != "gap" and not ids:
            continue  # a theme/contradiction/trend with no real source is unsupported
        tag = allowed.get((ins.tag or "").lower()) if ins.tag else None
        if ins.kind == "gap" and tag is None:
            continue  # a gap must name a Lens tag so it lines up with the coverage bars
        title, detail = ins.title.strip(), ins.detail.strip()
        if not title or not detail:
            continue
        # Evidence must be copied from the digest. This prevents a valid source id from
        # becoming a citation for an unsupported claim.
        evidence = []
        seen_evidence = set()
        for ev in ins.evidence:
            if ev.source_id not in ids:
                continue
            quote = ev.quote.strip()
            key = _norm(quote)
            if not key or key in seen_evidence:
                continue
            records = source_map[ev.source_id].get("quote_records", [])
            match = next((q for q in records if _norm(q["quote"]) == key), None)
            if match is None:
                continue
            seen_evidence.add(key)
            sid = ev.source_id
            if source_map[sid]["type"] in ("youtube", "audio"):
                app_link = f"/sources/{sid}?t={match['ts_s']}"
            else:
                app_link = f"/sources/{sid}#seg-{match['segment_id']}"
            evidence.append({"source_id": sid, "source_title": source_map[sid]["title"],
                             "source_type": source_map[sid]["type"], "quote": match["quote"],
                             "role": ev.role, "app_link": app_link,
                             "timestamp_s": match["ts_s"]})
        if ins.kind != "gap" and not evidence:
            continue
        if ins.kind == "contradiction" and len({e["source_id"] for e in evidence}) < 2:
            continue
        confidence = ins.confidence
        evidence_sources = {e["source_id"] for e in evidence}
        if len(evidence_sources) >= 3 and confidence == "low":
            confidence = "medium"
        if len(evidence_sources) < 2 and confidence == "high":
            confidence = "medium"
        sources = [{"source_id": i, "source_title": source_map[i]["title"],
                    "source_type": source_map[i]["type"],
                    "published_at": source_map[i]["published_at"].isoformat()
                    if source_map[i]["published_at"] else None,
                    "app_link": f"/sources/{i}"} for i in ids]
        result.append({"kind": ins.kind, "title": title, "detail": detail, "tag": tag, "sources": sources,
                       "evidence": evidence, "confidence": confidence,
                       "recommended_action": ins.recommended_action.strip() if ins.recommended_action else None})
    return result


def build_user_message(college: str, sources: list[dict], cov: list[dict]) -> str:
    lines = [f"<college>{college}</college>", "<coverage>"]
    for c in cov:
        lines.append(f"{c['tag']}: {c['sources']} source(s){' (gap)' if c['gap'] else ''}")
    lines.append("</coverage>")
    lines.append("<sources>")
    for s in sources:
        when = s["published_at"].isoformat() if s["published_at"] else "undated"
        head = f"[{s['id']}] \"{s['title']}\" · {s['type']} · priority={s.get('priority', 'normal')} · {when}"
        if s.get("host"):
            head += f" · {s['host']}"
        lines.append(head)
        if s.get("overview"):
            lines.append(f"overview: {s['overview']}")
        if s.get("chapters"):
            lines.append("chapters: " + "; ".join(f"{t} — {sm}" for t, sm in s["chapters"][:MAX_CHAPTERS]))
        if s.get("quotes"):
            lines.append("evidence_quotes: " + " | ".join(f'"{q}"' for q in s["quotes"][:MAX_QUOTES]))
        lines.append("")
    lines.append("</sources>")
    return "\n".join(lines)


# ---- DB + model orchestration ----

def _fetch_sources(collection_id: str) -> list[dict]:
    with pool().connection() as conn:
        srcs = conn.execute(
            """SELECT s.id, coalesce(s.title, s.label, s.url) AS title, s.type, s.priority, s.published_at, s.host, s.overview,
                      (SELECT count(*) FROM segments g WHERE g.source_id = s.id) AS segment_count,
                      (SELECT coalesce(array_agg(DISTINCT t), '{}')
                         FROM segments g CROSS JOIN unnest(g.tags) AS t WHERE g.source_id = s.id) AS tags
               FROM sources s
               WHERE s.collection_id = %s AND NOT s.archived AND s.status = 'ready'
               ORDER BY s.id""", (collection_id,)).fetchall()
        if not srcs:
            return []
        ids = [s["id"] for s in srcs]
        chapters = conn.execute(
            "SELECT source_id, title, summary FROM chapters WHERE source_id = ANY(%s) ORDER BY source_id, ord",
            (ids,)).fetchall()
        quotes = conn.execute(
            "SELECT source_id, segment_id, ts_s, quote, is_advice FROM key_quotes WHERE source_id = ANY(%s) ORDER BY source_id, id",
            (ids,)).fetchall()
    ch_by: dict[int, list] = {}
    for c in chapters:
        ch_by.setdefault(c["source_id"], []).append((c["title"], c["summary"]))
    q_by: dict[int, list] = {}
    for q in quotes:
        q_by.setdefault(q["source_id"], []).append(q["quote"])
    for s in srcs:
        s["chapters"] = ch_by.get(s["id"], [])
        s["quotes"] = q_by.get(s["id"], [])
        s["quote_records"] = [q for q in quotes if q["source_id"] == s["id"]][:MAX_QUOTES]
        s["tags"] = list(s["tags"] or [])
    return srcs


def _mark_running(collection_id: str) -> None:
    with pool().connection() as conn:
        conn.execute(
            """INSERT INTO collection_analyses (collection_id, status) VALUES (%s, 'running')
               ON CONFLICT (collection_id) DO UPDATE SET status = 'running', error = NULL""",
            (collection_id,))


def _save_empty(collection_id: str) -> None:
    with pool().connection() as conn:
        conn.execute(
            """INSERT INTO collection_analyses (collection_id, status, source_count, segment_count, consensus,
                                                insights, coverage, timeline, error, latency_ms, generated_at)
               VALUES (%s, 'empty', 0, 0, NULL, '[]', '[]', '[]', NULL, NULL, now())
               ON CONFLICT (collection_id) DO UPDATE SET status = 'empty', source_count = 0, segment_count = 0,
                 consensus = NULL, insights = '[]', coverage = '[]', timeline = '[]', error = NULL,
                 latency_ms = NULL, generated_at = now()""",
            (collection_id,))


def _save_failed(collection_id: str, error: str, cov: list[dict] | None = None,
                 tl: list[dict] | None = None, source_count: int = 0, segment_count: int = 0) -> None:
    """Flip status to failed but still persist the deterministic Atlas (coverage/timeline/counts),
    which needs no model — so a model outage never leaves the home page empty. Previous insight
    cards and generated_at are left untouched."""
    with pool().connection() as conn:
        conn.execute(
            """INSERT INTO collection_analyses (collection_id, status, error, source_count, segment_count,
                                                coverage, timeline)
               VALUES (%s, 'failed', %s, %s, %s, %s, %s)
               ON CONFLICT (collection_id) DO UPDATE SET status = 'failed', error = excluded.error,
                 source_count = excluded.source_count, segment_count = excluded.segment_count,
                 coverage = excluded.coverage, timeline = excluded.timeline""",
            (collection_id, error, source_count, segment_count, Jsonb(cov or []), Jsonb(tl or [])))


def _save_ready(collection_id: str, insights: list[dict], cov: list[dict], tl: list[dict],
                cons: int, model: str, source_count: int, segment_count: int, latency_ms: int) -> None:
    with pool().connection() as conn:
        conn.execute(
            """INSERT INTO collection_analyses (collection_id, status, model, source_count, segment_count,
                                                consensus, insights, coverage, timeline, error, latency_ms, generated_at)
               VALUES (%s, 'ready', %s, %s, %s, %s, %s, %s, %s, NULL, %s, now())
               ON CONFLICT (collection_id) DO UPDATE SET status = 'ready', model = excluded.model,
                 source_count = excluded.source_count, segment_count = excluded.segment_count,
                 consensus = excluded.consensus, insights = excluded.insights, coverage = excluded.coverage,
                 timeline = excluded.timeline, error = NULL, latency_ms = excluded.latency_ms,
                 generated_at = now()""",
            (collection_id, model, source_count, segment_count, cons,
             Jsonb(insights), Jsonb(cov), Jsonb(tl), latency_ms))


def run(collection_id: str) -> None:
    """Regenerate a collection's insights. Safe to call with no ready sources (stores an empty result)."""
    try:
        col = load_collection(collection_id)
    except (FileNotFoundError, ConfigError) as e:
        log.warning("insights: skipping %s (%s)", collection_id, e)
        return
    _mark_running(collection_id)
    sources = _fetch_sources(collection_id)
    if not sources:
        _save_empty(collection_id)
        log.info("insights %s: no ready sources yet", collection_id)
        return
    lens_tags = col.lens.tags
    cov = coverage(lens_tags, [set(s["tags"]) for s in sources])
    tl = timeline([s["published_at"] for s in sources])
    seg_count = sum(s["segment_count"] for s in sources)
    atlas = {"cov": cov, "tl": tl, "source_count": len(sources), "segment_count": seg_count}
    try:
        system = llm.prompt("synthesize", lens=col.lens_text, tags=", ".join(lens_tags))
        user = build_user_message(col.name, sources, cov)
        out, model, ms = llm.parse(settings.analysis_model, "medium", system, user, InsightsOut)
    except (ModelRefusal, ModelUnavailable) as e:
        _save_failed(collection_id, str(e), **atlas)
        log.warning("insights %s failed: %s", collection_id, e)
        return
    except anthropic.APIStatusError as e:
        _save_failed(collection_id, api_error_message(e), **atlas)
        log.warning("insights %s: %s", collection_id, e.message)
        return
    except Exception as e:  # noqa: BLE001 - last-resort guard so a bad run never crashes the pool
        _save_failed(collection_id, f"Unexpected error: {type(e).__name__}: {str(e)[:200]}", **atlas)
        log.exception("insights %s crashed", collection_id)
        return
    source_map = {s["id"]: s for s in sources}
    insights = prioritize(check(out, source_map, lens_tags))
    _save_ready(collection_id, insights, cov, tl, consensus(insights), model, len(sources), seg_count, ms)
    log.info("insights %s ready: %d insights over %d sources", collection_id, len(insights), len(sources))
