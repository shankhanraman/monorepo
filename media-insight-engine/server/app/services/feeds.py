"""Podcast RSS feeds → episodes with audio (FR-2.1). One feed entry in the YAML becomes N sources."""
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree  # feeds are untrusted XML

from app.services.urls import AUDIO_EXT

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
MAX_BYTES = 20 * 1024 * 1024
UA = "Mozilla/5.0 (media-insight-engine)"


class FeedError(Exception):
    pass


@dataclass
class Episode:
    url: str                  # the audio enclosure
    title: str
    published_at: date | None
    duration_s: int | None


@dataclass
class Feed:
    title: str | None
    episodes: list[Episode]   # newest first


def duration(text: str | None) -> int | None:
    """itunes:duration: '1:02:03', '62:03' or '3723'."""
    if not text or not re.fullmatch(r"\d+(:\d+){0,2}", text.strip()):
        return None
    seconds = 0
    for part in text.strip().split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def parse(xml: bytes) -> Feed:
    try:
        root = ElementTree.fromstring(xml)
    except Exception as e:
        raise FeedError(f"not valid XML ({e})") from e
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise FeedError("not an RSS feed")
    episodes = []
    for item in channel.findall("item"):
        enc = item.find("enclosure")
        url = (enc.get("url") if enc is not None else "") or ""
        kind = (enc.get("type") if enc is not None else "") or ""
        if not url or not (kind.startswith("audio") or url.lower().split("?")[0].endswith(AUDIO_EXT)):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", "")).date()
        except (TypeError, ValueError):
            published = None
        episodes.append(Episode(url.strip(), (item.findtext("title") or url).strip(), published,
                                duration(item.findtext(f"{ITUNES}duration"))))
    episodes.sort(key=lambda e: e.published_at or date.min, reverse=True)
    return Feed((channel.findtext("title") or "").strip() or None, episodes)


def select(feed: Feed, n: int, match: str | None) -> list[Episode]:
    eps = [e for e in feed.episodes if not match or re.search(match, e.title, re.IGNORECASE)]
    return eps[:n]


def fetch(url: str) -> Feed:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(MAX_BYTES + 1)
    except Exception as e:
        raise FeedError(f"could not download ({e})") from e
    if len(data) > MAX_BYTES:
        raise FeedError("feed is larger than 20 MB")
    return parse(data)
