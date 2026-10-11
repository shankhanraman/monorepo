from app.services.analyze import ChapterOut, QuoteOut, SegmentOut, SourceAnalysis, check, quote_second
from app.services.segment import by_heading, by_time, clean_markdown


def lines(n_seconds: int, step: int = 5):
    return [{"start": t + 0.5, "dur": step, "text": f"word{t}"} for t in range(0, n_seconds, step)]


def test_by_time_makes_one_segment_per_minute():
    segs = by_time(lines(2100), 60, duration_s=2112)            # a 35-minute video
    assert len(segs) == 35
    assert (segs[0].start_s, segs[0].end_s) == (0, 60)
    assert (segs[34].start_s, segs[34].end_s) == (2040, 2100)
    assert segs[12].text.startswith("word720") and segs[12].lines[0]["start"] == 720.5


def test_by_time_skips_silent_windows_and_caps_end():
    segs = by_time([{"start": 5, "dur": 2, "text": "hi"}, {"start": 130, "dur": 4, "text": "  there \n "}], 60)
    assert [(s.ord, s.start_s, s.end_s, s.text) for s in segs] == [(0, 0, 60, "hi"), (1, 120, 134, "there")]


MD = """[ Skip to main content](https://x.edu/#main)
Home
# Essay Topics
## Short answer questions
  * Tell us about a **topic** or [idea](https://x.edu/idea) that excites you.
  * Why Yale? (125 words)
![logo](logo.png)
## Testing
""" + "\n".join(f"Sentence number {i} about testing policy and scores." for i in range(60))


def test_by_heading_sections_nav_and_long_split():
    segs = by_heading(MD, max_words=120)
    assert segs[0].anchor is None and segs[0].text == "Home"          # nav link line dropped
    short = next(s for s in segs if s.anchor == "Short answer questions")
    assert short.text == "Tell us about a topic or idea that excites you.\nWhy Yale? (125 words)"
    testing = [s for s in segs if s.anchor == "Testing"]
    assert len(testing) > 1 and all(len(s.text.split()) <= 120 for s in testing)
    assert [s.ord for s in segs] == list(range(len(segs))) and all(s.start_s == s.ord for s in segs)


def test_clean_markdown():
    assert clean_markdown("**Bold** and _it_ and `code` [link](http://a.b/(x))") == "Bold and it and code link"


def make_segs():
    return by_time([{"start": 0, "dur": 5, "text": "Welcome everyone"},
                    {"start": 61, "dur": 5, "text": "we really want to hear"},
                    {"start": 66, "dur": 5, "text": "what got you curious in the first place."},
                    {"start": 125, "dur": 5, "text": "Testing is optional"}], 60, duration_s=180)


def test_quote_second_finds_the_caption_line():
    segs = make_segs()
    assert quote_second("What got you CURIOUS in the first place", segs[1]) == 66
    assert quote_second("we really want to hear what got you curious", segs[1]) == 61
    assert quote_second("something never said", segs[1]) is None


def test_check_keeps_only_grounded_output():
    segs = make_segs()
    out = SourceAnalysis(
        overview=" Two officers. ",
        chapters=[ChapterOut(first_seg=1, last_seg=2, title="Essays", summary="s"),
                  ChapterOut(first_seg=0, last_seg=0, title="Intro", summary="s"),
                  ChapterOut(first_seg=2, last_seg=5, title="Out of range", summary="s"),
                  ChapterOut(first_seg=2, last_seg=2, title="Overlaps", summary="s")],
        segments=[SegmentOut(i=1, summary="Curiosity matters", tags=["Essays", "made-up"]),
                  SegmentOut(i=9, summary="no such segment", tags=[])],
        key_quotes=[QuoteOut(seg=1, quote="what got you curious in the first place", is_advice=True),
                    QuoteOut(seg=1, quote="an invented quote", is_advice=True),
                    QuoteOut(seg=7, quote="Testing is optional", is_advice=False)])
    r = check(out, segs, ["testing", "essays"])
    assert r["overview"] == "Two officers."
    assert [(c["title"], c["start_s"], c["end_s"]) for c in r["chapters"]] == [("Intro", 0, 60), ("Essays", 60, 180)]
    assert r["segments"] == {1: {"summary": "Curiosity matters", "tags": ["essays"]}}
    assert r["key_quotes"] == [{"seg": 1, "ts_s": 66, "quote": "what got you curious in the first place",
                                "is_advice": True}]
