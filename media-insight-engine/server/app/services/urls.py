"""URL normalization (the de-duplication key, FR-2.5) and type detection (FR-2.1)."""
import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_DROP_PARAMS = {"fbclid", "gclid"}
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".opus")
AUDIO_HOSTS = ("podcasts.apple.com",)          # podcast pages yt-dlp can download from


def youtube_id(url: str) -> str | None:
    u = urlsplit(url.strip())
    host = (u.hostname or "").lower()
    vid = None
    if host == "youtu.be":
        vid = u.path.lstrip("/").split("/")[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if u.path == "/watch":
            vid = parse_qs(u.query).get("v", [None])[0]
        elif u.path.startswith(("/shorts/", "/embed/", "/live/")):
            vid = u.path.split("/")[2]
    return vid if vid and _YT_ID.match(vid) else None


def normalize(url: str) -> str:
    """Raise ValueError when the URL isn't http(s)."""
    vid = youtube_id(url)
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    u = urlsplit(url.strip())
    if u.scheme.lower() not in ("http", "https") or not u.hostname:
        raise ValueError("not an http(s) URL")
    netloc = u.hostname.lower() + (f":{u.port}" if u.port else "")
    query = urlencode([(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                       if not k.lower().startswith("utm_") and k.lower() not in _DROP_PARAMS])
    path = u.path.rstrip("/") or "/"
    return urlunsplit((u.scheme.lower(), netloc, path, query, ""))


def detect_type(url: str) -> str:
    """youtube | web | audio | pdf | rss | spotify (spotify is rejected: its audio is DRM-protected)."""
    if youtube_id(url):
        return "youtube"
    u = urlsplit(url)
    host, path = (u.hostname or "").lower(), u.path.lower()
    if host.endswith("spotify.com"):
        return "spotify"
    if path.endswith((".rss", ".xml")) or re.search(r"/(feed|rss)(/|$)", path) or host.startswith(("feeds.", "rss.")):
        return "rss"
    if path.endswith(AUDIO_EXT) or host in AUDIO_HOSTS:
        return "audio"
    if path.endswith(".pdf"):
        return "pdf"
    return "web"
