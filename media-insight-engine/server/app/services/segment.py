"""Cut transcripts into time windows and web pages into sections (FR-3.3). Raw text is kept as-is."""
import re
from dataclasses import dataclass, field


@dataclass
class Seg:
    ord: int
    start_s: int
    end_s: int
    text: str
    anchor: str | None = None
    lines: list[dict] = field(default_factory=list)  # video: caption lines [{start, text}]


def by_time(lines: list[dict], seconds: int, duration_s: int | None = None) -> list[Seg]:
    """lines: [{start: float, dur: float, text: str}] in time order → one segment per non-empty window."""
    buckets: dict[int, list[dict]] = {}
    for line in lines:
        text = " ".join(line["text"].split())
        if text:
            buckets.setdefault(int(line["start"] // seconds), []).append({"start": line["start"], "text": text})
    last_end = max((l["start"] + l.get("dur", 0) for l in lines), default=0)
    end_cap = duration_s or int(last_end + 0.999)
    segs = []
    for n, idx in enumerate(sorted(buckets)):
        start = idx * seconds
        segs.append(Seg(n, start, max(start + 1, min(start + seconds, end_cap)),
                        " ".join(l["text"] for l in buckets[idx]), lines=buckets[idx]))
    return segs


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def clean_markdown(text: str) -> str:
    """Markdown → plain text, so stored text matches what the page shows (needed for #:~:text= links)."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                  # images
    text = re.sub(r"\[([^\]]*)\]\((?:[^()]|\([^)]*\))*\)", r"\1", text)  # links → their text
    text = re.sub(r"<[^>]+>", "", text)                                # stray html
    text = re.sub(r"(\*\*|__|\*|_|`)(\S.*?\S|\S)\1", r"\2", text)      # emphasis / code
    text = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", text, flags=re.M)     # list markers
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)                   # quotes
    text = re.sub(r"^\s*\|?[-:| ]{3,}\|?\s*$", "", text, flags=re.M)   # table rules
    text = text.replace("|", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def by_heading(markdown: str, max_words: int = 350) -> list[Seg]:
    """Split at headings; long sections are split again at paragraph boundaries."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for raw in markdown.splitlines():
        m = _HEADING.match(raw)
        if m:
            sections.append((clean_markdown(m.group(2)) or None, []))
        else:
            sections[-1][1].append(raw)
    segs: list[Seg] = []
    for heading, body in sections:
        paragraphs = [clean_markdown(line) for line in body if not _is_nav(line)]
        paragraphs = [p for p in paragraphs if p]
        chunk: list[str] = []
        for p in paragraphs:
            if chunk and len(" ".join(chunk + [p]).split()) > max_words:
                segs.append(Seg(len(segs), len(segs), len(segs), "\n".join(chunk), heading))
                chunk = []
            chunk.append(p)
        if chunk:
            segs.append(Seg(len(segs), len(segs), len(segs), "\n".join(chunk), heading))
    return segs


def by_page(pages: list[str], max_words: int = 350) -> list[Seg]:
    """PDF: one segment per page (anchor "Page N"); long pages are split at line boundaries."""
    segs: list[Seg] = []
    for number, text in enumerate(pages, start=1):
        chunk: list[str] = []
        for line in (l for l in text.splitlines() if l.strip()):
            if chunk and len(" ".join(chunk + [line]).split()) > max_words:
                segs.append(Seg(len(segs), len(segs), len(segs), "\n".join(chunk), f"Page {number}"))
                chunk = []
            chunk.append(line)
        if chunk:
            segs.append(Seg(len(segs), len(segs), len(segs), "\n".join(chunk), f"Page {number}"))
    return segs


def _is_nav(line: str) -> bool:
    """Menu / breadcrumb lines: nothing but links ('[ Skip to main content](…)')."""
    if "](" not in line:
        return False
    rest = re.sub(r"\[[^\]]*\]\((?:[^()]|\([^)]*\))*\)", "", line)
    return len(re.findall(r"\w+", rest)) <= 1
