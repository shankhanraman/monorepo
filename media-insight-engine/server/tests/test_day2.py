"""Day 2: RSS feeds, sync with feeds, transcription progress, PDF pages, audio/PDF links, HTML report."""
from datetime import date, datetime

import pytest

from app.config import load_collection
from app.services import feeds
from app.services.audio import progress_reporter
from app.services.banks import report_html
from app.services.links import app_link, deep_link, position_label
from app.services.qa_graph import AnswerDraft, finalize
from app.services.segment import by_page
from app.services.sync import plan_sync
from app.services.urls import detect_type
from tests.conftest import write

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
  <title>Inside the Yale Admissions Office</title>
  <item><title>Ep 40: Testing</title><pubDate>Mon, 03 Mar 2025 10:00:00 GMT</pubDate>
        <enclosure url="https://cdn.example.com/ep40.mp3" type="audio/mpeg" length="1"/><itunes:duration>35:02</itunes:duration></item>
  <item><title>Ep 42: Supplemental essays</title><pubDate>Tue, 02 Sep 2025 10:00:00 GMT</pubDate>
        <enclosure url="https://cdn.example.com/ep42.mp3?utm_source=feed" type="audio/mpeg" length="1"/><itunes:duration>2160</itunes:duration></item>
  <item><title>Ep 41: Why major</title><pubDate>not a date</pubDate>
        <enclosure url="https://cdn.example.com/ep41.m4a" type="" length="1"/><itunes:duration>1:00:05</itunes:duration></item>
  <item><title>Blog post, no audio</title><pubDate>Wed, 01 Oct 2025 10:00:00 GMT</pubDate></item>
</channel></rss>"""
FEED_URL = "https://feeds.example.com/yale"


def test_parse_feed_newest_first_audio_only():
    f = feeds.parse(FEED)
    assert f.title == "Inside the Yale Admissions Office"
    assert [(e.title, e.published_at, e.duration_s) for e in f.episodes] == [
        ("Ep 42: Supplemental essays", date(2025, 9, 2), 2160),
        ("Ep 40: Testing", date(2025, 3, 3), 2102),
        ("Ep 41: Why major", None, 3605)]                       # unknown dates last; no-audio item skipped
    assert [e.title for e in feeds.select(f, 1, None)] == ["Ep 42: Supplemental essays"]
    assert [e.title for e in feeds.select(f, 5, "testing|MAJOR")] == ["Ep 40: Testing", "Ep 41: Why major"]


@pytest.mark.parametrize("bad, message", [(b"<html>nope</html>", "not an RSS feed"), (b"<rss", "not valid XML"),
                                          (b'<!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel/></rss>', "not valid XML")])
def test_bad_feeds(bad, message):
    with pytest.raises(feeds.FeedError, match=message):
        feeds.parse(bad)


def test_duration_formats():
    assert [feeds.duration(t) for t in ("62:03", "1:02:03", "3723", "", None, "1h")] == [3723, 3723, 3723, None, None, None]


def collection(config_dir, sources: str):
    write(config_dir / "collections" / "yale.yaml", "name: Yale\nlens: test-lens\nsources:\n" + sources)
    return load_collection("yale", config_dir)


def test_sync_expands_feed_into_episodes(config_dir):
    col = collection(config_dir, f"  - url: {FEED_URL}\n    type: rss\n    episodes: 2\n    priority: high\n")
    existing = {"https://cdn.example.com/ep40.mp3": {"id": 5, "status": "ready", "archived": False, "error": None,
                                                     "feed_url": FEED_URL}}
    steps = plan_sync(col, existing, {FEED_URL: feeds.parse(FEED)})
    assert [(s.action, s.label, s.reason) for s in steps] == [
        ("feed", "Inside the Yale Admissions Office", "Feed read: 2 of 3 episodes selected (latest 2)"),
        ("queued", "Ep 42: Supplemental essays", "New episode"),
        ("skipped", "Ep 40: Testing", "Already ready")]
    ep = steps[1]
    assert (ep.url, ep.type, ep.feed_url, ep.published_at, ep.duration_s) == (
        "https://cdn.example.com/ep42.mp3", "audio", FEED_URL, date(2025, 9, 2), 2160)
    assert ep.media_url == "https://cdn.example.com/ep42.mp3?utm_source=feed"  # original URL kept for playback


def test_feed_episodes_kept_until_feed_removed(config_dir):
    old = {"https://cdn.example.com/old.mp3": {"id": 9, "status": "ready", "archived": False, "error": None,
                                               "feed_url": FEED_URL}}
    col = collection(config_dir, f"  - url: {FEED_URL}\n    type: rss\n    episodes: 1\n")
    assert all(s.action != "archived" for s in plan_sync(col, old, {FEED_URL: feeds.parse(FEED)}))
    assert all(s.action != "archived" for s in plan_sync(col, old, {FEED_URL: "timed out"}))   # network blip
    col = collection(config_dir, "  - url: https://x.edu/page\n")
    assert [s.action for s in plan_sync(col, old, {})].count("archived") == 1


def test_feed_problems_are_logged(config_dir):
    col = collection(config_dir, f"""\
  - url: {FEED_URL}
    type: rss
  - url: https://open.spotify.com/show/abc
  - url: https://feeds.example.com/empty
    type: rss
  - url: https://feeds.example.com/x
    type: rss
    match: "(unclosed"
""")
    empty = feeds.Feed("Empty", [])
    steps = plan_sync(col, {}, {FEED_URL: "could not download (HTTP Error 404)", "https://feeds.example.com/empty": empty})
    reasons = [(s.action, s.reason) for s in steps]
    assert reasons[0] == ("failed", "Could not read feed: could not download (HTTP Error 404)")
    assert reasons[1] == ("failed", "Spotify audio is DRM-protected: use the show's RSS feed instead")
    assert reasons[2] == ("failed", "Feed has no episodes with audio")
    assert reasons[3][0] == "failed" and "invalid regex" in reasons[3][1]


@pytest.mark.parametrize("url, kind", [
    ("https://feeds.megaphone.fm/abc", "rss"), ("https://x.org/podcast.rss", "rss"), ("https://x.org/feed.xml", "rss"),
    ("https://yalepodcasts.blubrry.net/category/inside_yale_admissions/feed/podcast/", "rss"),  # the real Yale feed
    ("https://x.org/feedback-form", "web"),
    ("https://podcasts.apple.com/us/podcast/x/id1?i=2", "audio"), ("https://x.org/a.M4A", "audio"),
    ("https://open.spotify.com/episode/1", "spotify"), ("https://oir.yale.edu/cds.pdf", "pdf"),
])
def test_detect_day2_types(url, kind):
    assert detect_type(url) == kind


def test_progress_reporter_steps_and_never_100():
    seen = []
    update = progress_reporter(100.0, seen.append, every=5)
    for t in (0, 1, 4.9, 5, 12, 13, 50, 99.9, 100):
        update(t)
    assert seen == [0, 5, 12, 50, 99]
    zero = []
    progress_reporter(0, zero.append)(10)
    assert zero == [0]


def test_by_page():
    long_page = "\n".join(f"line {i} " + "word " * 20 for i in range(40))
    segs = by_page(["Cover page text", "", long_page])
    assert segs[0].anchor == "Page 1" and segs[0].text == "Cover page text"
    page3 = [s for s in segs if s.anchor == "Page 3"]
    assert len(page3) > 1 and all(len(s.text.split()) <= 350 for s in page3)
    assert [s.ord for s in segs] == list(range(len(segs))) and all(s.start_s == s.ord for s in segs)


def test_audio_and_pdf_links():
    audio = {"id": 21, "type": "audio", "url": "https://cdn.x/ep.mp3", "media_url": "https://cdn.x/ep.mp3?t=1", "ext_id": None}
    assert deep_link(audio, 180.6) == "https://cdn.x/ep.mp3?t=1#t=180"
    assert app_link(audio, 180, 7) == "/sources/21?t=180"
    assert position_label("audio", 180, 240, None) == "3:00–4:00"
    pdf = {"id": 22, "type": "pdf", "url": "https://x.edu/cds.pdf", "ext_id": None}
    assert deep_link(pdf, 4, "text", "Page 12") == "https://x.edu/cds.pdf#page=12"
    assert app_link(pdf, 4, 99) == "/sources/22#seg-99"
    assert position_label("pdf", 4, 4, "Page 12") == "Page 12"


def test_report_html_escapes_everything():
    hit = {"segment_id": 1, "source_id": 2, "collection_id": "yale", "type": "pdf", "url": "https://x.edu/a.pdf",
           "ext_id": None, "host": "x", "published_at": None, "source_title": "<script>alert(1)</script>",
           "start_s": 0, "end_s": 0, "anchor": "Page 1", "text": "t", "summary": None, "tags": []}
    r = finalize("Q <b>?", AnswerDraft(coverage="strong", answer_md="A & B [1].", conflicts=None), [hit],
                 date(2026, 10, 12), 18, "Yale", False)
    run = {"id": 1, "bank_name": "Bank <i>", "collection_id": "yale", "created_at": datetime(2026, 10, 12),
           "items": [{"index": 0, "question": "Q <b>?", "status": "done", "answer_md": r["answer_md"],
                      "coverage": "strong", "watch": r["watch"], "stale_warning": r["stale_warning"], "error": None}]}
    out = report_html(run)
    assert "<script>" not in out and "&lt;script&gt;" in out and "Q &lt;b&gt;?" in out and "A &amp; B [1]." in out
    assert "href='https://x.edu/a.pdf#page=1'" in out and "Page 1" in out
