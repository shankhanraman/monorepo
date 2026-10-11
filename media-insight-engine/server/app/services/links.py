"""Deep links, in-app links and position labels (FR-4.3, PRD §5 'Deep links')."""
import re
from urllib.parse import quote

TIMED = ("youtube", "audio")  # sources whose start_s/end_s are seconds


def fmt_time(seconds: int) -> str:
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def text_fragment(text: str, words: int = 6) -> str:
    """#:~:text= value from the first words of a snippet; '-', ',' and '&' must be escaped."""
    first = " ".join(re.findall(r"\S+", text)[:words])
    return quote(first, safe="").replace("-", "%2D")


def page_number(anchor: str | None) -> int:
    m = re.search(r"\d+", anchor or "")
    return int(m.group()) if m else 1


def deep_link(source: dict, start_s: int, text: str = "", anchor: str | None = None) -> str:
    kind = source["type"]
    if kind == "youtube":
        return f"https://youtu.be/{source['ext_id']}?t={int(start_s)}"
    if kind == "audio":  # media fragment: the browser starts playback there
        return f"{source.get('media_url') or source['url']}#t={int(start_s)}"
    if kind == "pdf":
        return f"{source['url']}#page={page_number(anchor)}"
    return f"{source['url']}#:~:text={text_fragment(text)}" if text.strip() else source["url"]


def app_link(source: dict, start_s: int, segment_id: int) -> str:
    if source["type"] in TIMED:
        return f"/sources/{source['id']}?t={int(start_s)}"
    return f"/sources/{source['id']}#seg-{segment_id}"


def position_label(source_type: str, start_s: int, end_s: int, anchor: str | None) -> str:
    if source_type in TIMED:
        return f"{fmt_time(start_s)}–{fmt_time(end_s)}"
    return anchor or f"Section {start_s + 1}"


def snippet(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"
