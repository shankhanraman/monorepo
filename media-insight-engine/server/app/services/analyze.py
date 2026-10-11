"""Per-source analysis through the Lens (FR-3) + the checks that keep it grounded."""
import re

from pydantic import BaseModel

from app.config import settings
from app.services import llm
from app.services.links import fmt_time
from app.services.segment import Seg


class ChapterOut(BaseModel):
    first_seg: int
    last_seg: int
    title: str
    summary: str


class SegmentOut(BaseModel):
    i: int
    summary: str
    tags: list[str]


class QuoteOut(BaseModel):
    seg: int
    quote: str
    is_advice: bool


class SourceAnalysis(BaseModel):
    overview: str
    chapters: list[ChapterOut]
    segments: list[SegmentOut]
    key_quotes: list[QuoteOut]


def build_user_message(source: dict, segs: list[Seg]) -> str:
    kind = "video transcript" if source["type"] == "youtube" else "web page"
    head = (f"<source>\ntitle: {source.get('title') or source.get('label') or source['url']}\n"
            f"by: {source.get('host') or 'unknown'}\npublished: {source.get('published_at') or 'unknown'}\n"
            f"kind: {kind}\n</source>\n<segments>\n")
    body = []
    for s in segs:
        where = (f"{fmt_time(s.start_s)}–{fmt_time(s.end_s)}" if source["type"] == "youtube"
                 else f"section: {s.anchor or '(no heading)'}")
        body.append(f"[{s.ord}] {where}\n{s.text}")
    return head + "\n\n".join(body) + "\n</segments>"


def run(source: dict, lens_text: str, lens_tags: list[str], segs: list[Seg]) -> tuple[dict, str]:
    system = llm.prompt("analyze", lens=lens_text, tags=", ".join(lens_tags))
    # ponytail: one non-streaming call (16k output incl. thinking) fits ~150 segments (~2.5 h);
    # split into chunks or switch to streaming if longer sources show up.
    out, model, _ = llm.parse(settings.analysis_model, "medium", system, build_user_message(source, segs),
                              SourceAnalysis)
    return check(out, segs, lens_tags), model


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def quote_second(quote: str, seg: Seg) -> int | None:
    """Second where a verbatim quote starts inside the segment, or None if it isn't really there."""
    q = _norm(quote)
    if not q:
        return None
    if not seg.lines:  # web: no timing inside a section
        return seg.start_s if q in _norm(seg.text) else None
    joined, starts = "", []
    for line in seg.lines:
        starts.append((len(joined), line["start"]))
        joined += _norm(line["text"]) + " "
    pos = joined.find(q)
    if pos < 0:
        return None
    return int(max(start for offset, start in starts if offset <= pos))


def check(out: SourceAnalysis, segs: list[Seg], lens_tags: list[str]) -> dict:
    """Model output → only what the segments support (datamodels.md §3.1)."""
    n = len(segs)
    allowed = {t.lower(): t for t in lens_tags}
    chapters, last = [], -1
    for c in sorted(out.chapters, key=lambda c: c.first_seg):
        if 0 <= c.first_seg <= c.last_seg < n and c.first_seg > last:
            chapters.append({"start_s": segs[c.first_seg].start_s, "end_s": segs[c.last_seg].end_s,
                             "title": c.title.strip(), "summary": c.summary.strip()})
            last = c.last_seg
    seg_info = {}
    for s in out.segments:
        if 0 <= s.i < n:
            tags = [allowed[t.lower()] for t in s.tags if t.lower() in allowed]
            seg_info[s.i] = {"summary": s.summary.strip() or None, "tags": list(dict.fromkeys(tags))}
    quotes, seen = [], set()
    for q in out.key_quotes:
        if not 0 <= q.seg < n or _norm(q.quote) in seen:
            continue
        ts = quote_second(q.quote, segs[q.seg])
        if ts is not None:
            seen.add(_norm(q.quote))
            quotes.append({"seg": q.seg, "ts_s": ts, "quote": q.quote.strip(), "is_advice": q.is_advice})
    return {"overview": out.overview.strip(), "chapters": chapters, "segments": seg_info, "key_quotes": quotes[:10]}
