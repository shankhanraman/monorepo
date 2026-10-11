import pytest

from app.services.links import deep_link, fmt_time, position_label, snippet, text_fragment
from app.services.urls import detect_type, normalize, youtube_id

V = "abcdefghijk"


@pytest.mark.parametrize("url", [
    f"https://youtu.be/{V}?t=30", f"https://www.youtube.com/watch?v={V}&list=PL1", f"https://m.youtube.com/watch?v={V}",
    f"https://youtube.com/shorts/{V}", f"https://www.youtube.com/embed/{V}",
])
def test_youtube_forms_normalize_to_one_url(url):
    assert youtube_id(url) == V
    assert normalize(url) == f"https://www.youtube.com/watch?v={V}"


@pytest.mark.parametrize("url, expected", [
    ("HTTPS://Admissions.Yale.edu/essays/?utm_source=x&a=1#top", "https://admissions.yale.edu/essays?a=1"),
    ("https://example.com/", "https://example.com/"),
    ("https://example.com/page?fbclid=1", "https://example.com/page"),
])
def test_web_normalization(url, expected):
    assert normalize(url) == expected


def test_non_http_rejected():
    with pytest.raises(ValueError):
        normalize("ftp://example.com/file")


@pytest.mark.parametrize("url, kind", [
    (f"https://youtu.be/{V}", "youtube"), ("https://example.com/ep.mp3", "audio"),
    ("https://example.com/podcast/feed", "rss"), ("https://example.com/x.pdf", "pdf"),
    ("https://admissions.yale.edu/essays", "web"),
])
def test_detect_type(url, kind):
    assert detect_type(url) == kind


def test_time_and_labels():
    assert fmt_time(0) == "0:00" and fmt_time(725) == "12:05" and fmt_time(3725) == "1:02:05"
    assert position_label("youtube", 720, 780, None) == "12:00–13:00"
    assert position_label("web", 3, 3, "Short answers") == "Short answers"
    assert position_label("web", 3, 3, None) == "Section 4"


def test_deep_links():
    assert deep_link({"type": "youtube", "ext_id": V, "url": ""}, 720.9) == f"https://youtu.be/{V}?t=720"
    link = deep_link({"type": "web", "url": "https://x.edu/essays", "ext_id": None},
                     0, "Tell us about a well-known, life-changing idea & more")
    assert link == "https://x.edu/essays#:~:text=Tell%20us%20about%20a%20well%2Dknown%2C%20life%2Dchanging"
    assert text_fragment("") == ""


def test_snippet_cuts_at_word():
    assert snippet("a " * 300, 20).endswith("…") and len(snippet("a " * 300, 20)) <= 21
