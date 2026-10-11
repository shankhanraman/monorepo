from datetime import date, datetime

from app.services.banks import report_markdown
from app.services.qa_graph import NOT_COVERED, AnswerDraft, build_graph, finalize, is_stale, search_query

TODAY = date(2026, 10, 11)


def hit(i: int, published=date(2026, 1, 1), kind="youtube"):
    return {"segment_id": 100 + i, "source_id": 10 + i, "collection_id": "yale", "type": kind,
            "url": f"https://x.edu/{i}", "ext_id": f"vid{i:08d}", "host": "Yale", "published_at": published,
            "source_title": f"Source {i}", "start_s": 60 * i, "end_s": 60 * i + 60, "anchor": None,
            "text": f"text of segment {i}", "summary": None, "tags": []}


def test_is_stale():
    assert not is_stale(date(2025, 4, 12), TODAY, 18)
    assert is_stale(date(2025, 4, 11), TODAY, 18)
    assert is_stale(None, TODAY, 18)


def test_finalize_strips_unknown_markers_and_renumbers():
    hits = [hit(0), hit(1), hit(2, published=date(2024, 1, 1))]
    draft = AnswerDraft(coverage="strong", answer_md="Origin story matters [3]. Be specific [1][7]. Invented [9].",
                        conflicts="Dates differ [3] vs [1].")
    r = finalize("q", draft, hits, TODAY, 18, "Yale", False)
    assert r["answer_md"] == "Origin story matters [1]. Be specific [2]. Invented."
    assert [(c["n"], c["segment_id"]) for c in r["citations"]] == [(1, 102), (2, 100)]
    assert r["conflicts"] == "Dates differ [1] vs [2]."
    assert r["citations"][0]["stale"] and not r["citations"][1]["stale"]
    assert "2024-01-01 is older than 18 months" in r["stale_warning"] and "official Yale admissions site" in r["stale_warning"]
    assert [c["n"] for c in r["watch"]] == [2, 1]                    # ranked by retrieval order
    assert r["citations"][1]["deep_link"] == "https://youtu.be/vid00000000?t=0"
    assert r["citations"][1]["app_link"] == "/sources/10?t=0" and r["citations"][1]["label"] == "0:00–1:00"
    assert not r["not_covered"] and r["label"] == "Summary of sources"


def test_finalize_not_covered_paths():
    hits = [hit(i) for i in range(5)]
    for draft in (AnswerDraft(coverage="none", answer_md="", conflicts=None),
                  AnswerDraft(coverage="strong", answer_md="Claims without citations.", conflicts=None),
                  AnswerDraft(coverage="partial", answer_md="Only bad refs [8].", conflicts=None), None):
        r = finalize("hockey?", draft, hits, TODAY, 18, "Yale", True)
        assert r["not_covered"] and r["answer_md"] == NOT_COVERED and r["coverage"] == "none"
        assert r["citations"] == [] and [c["n"] for c in r["closest"]] == [1, 2, 3]
        assert r["stale_warning"] is None and r["retried"]


def test_unknown_date_warning_and_web_links():
    h = hit(0, published=None, kind="web")
    h.update(anchor="Short answers", start_s=3, end_s=3)
    r = finalize("q", AnswerDraft(coverage="partial", answer_md="Yes [1].", conflicts=None), [h], TODAY, 18, None, False)
    c = r["citations"][0]
    assert c["label"] == "Short answers" and c["app_link"] == "/sources/10#seg-100"
    assert c["deep_link"] == "https://x.edu/0#:~:text=text%20of%20segment%200"
    assert "1 cited source has no publish date" in r["stale_warning"] and "official admissions site" in r["stale_warning"]


def run_graph(drafts, hits_by_attempt):
    calls = {"retrieve": [], "answer": 0, "rewrite": 0}

    def retrieve(collection, query, filters):
        calls["retrieve"].append(query)
        return hits_by_attempt[len(calls["retrieve"]) - 1]

    def answer(state):
        calls["answer"] += 1
        return drafts[calls["answer"] - 1], "fake-model"

    def rewrite(state):
        calls["rewrite"] += 1
        return "better query"

    g = build_graph(retrieve, answer, rewrite, today_fn=lambda: TODAY)
    out = g.invoke({"collection": "yale", "question": "q?", "query": "q?", "attempt": 0, "lens_text": "", "history": []})
    return out["result"], calls


def test_graph_strong_answer_goes_straight_to_finalize():
    r, calls = run_graph([AnswerDraft(coverage="strong", answer_md="A [1].", conflicts=None)], [[hit(0)]])
    assert calls == {"retrieve": ["q?"], "answer": 1, "rewrite": 0} and not r["retried"]


def test_graph_weak_answer_retries_once_with_rewritten_query():
    drafts = [AnswerDraft(coverage="none", answer_md="", conflicts=None),
              AnswerDraft(coverage="partial", answer_md="Found it [1].", conflicts=None)]
    r, calls = run_graph(drafts, [[hit(0)], [hit(1)]])
    assert calls == {"retrieve": ["q?", "better query"], "answer": 2, "rewrite": 1}
    assert r["retried"] and r["citations"][0]["segment_id"] == 101


def test_graph_gives_up_after_one_retry():
    none = AnswerDraft(coverage="none", answer_md="", conflicts=None)
    r, calls = run_graph([none, none], [[hit(0)], [hit(1)]])
    assert calls["rewrite"] == 1 and calls["answer"] == 2 and r["not_covered"]


def test_graph_no_hits_skips_the_model():
    r, calls = run_graph([], [[], []])
    assert calls["answer"] == 0 and calls["rewrite"] == 1 and r["not_covered"] and r["closest"] == []


def test_search_query_uses_previous_question():
    assert search_query("how long?", [{"question": "why major essay", "answer_md": "x"}]) == "why major essay how long?"
    assert search_query("q", []) == "q"


def test_report_markdown():
    done = finalize("Why major?", AnswerDraft(coverage="strong", answer_md="Be specific [1].", conflicts=None),
                    [hit(12)], TODAY, 18, "Yale", False)
    run = {"id": 7, "bank_name": "Yale supplements", "collection_id": "yale", "created_at": datetime(2026, 10, 11),
           "items": [{"index": 0, "question": "Why major?", "status": "done", "answer_md": done["answer_md"],
                      "coverage": "strong", "watch": done["watch"], "stale_warning": None, "error": None},
                     {"index": 1, "question": "Hockey?", "status": "failed", "answer_md": None, "coverage": None,
                      "watch": [], "stale_warning": None, "error": "timeout"}]}
    md = report_markdown(run)
    assert md.startswith("# Yale supplements\n")
    assert "## 1. Why major?\n**Coverage:** strong\n\nBe specific [1]." in md
    assert "1. [1] [Source 12 — 12:00–13:00](https://youtu.be/vid00000012?t=720) (2026-01-01)" in md
    assert "## 2. Hockey?\n_failed: timeout_" in md


def test_api_error_message_uses_claudes_reason():
    from types import SimpleNamespace
    from app.services.llm import api_error_message
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low."}}
    assert api_error_message(SimpleNamespace(body=body, message="raw dump")) == "Claude API error: Your credit balance is too low."
    assert api_error_message(SimpleNamespace(body=None, message="Overloaded")) == "Claude API error: Overloaded"
