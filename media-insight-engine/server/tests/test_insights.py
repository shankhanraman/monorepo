"""Pure-function tests for the collection synthesis agent (no DB, no model)."""
from datetime import date

from app.services.insights import (InsightOut, InsightsOut, check, consensus, coverage, prioritize,
                                    timeline)


def test_coverage_counts_distinct_sources_and_flags_gaps():
    rows = coverage(
        ["essays", "testing", "financial-aid"],
        [{"essays", "testing"}, {"essays"}, {"ESSAYS"}],  # case-insensitive
    )
    by_tag = {r["tag"]: r for r in rows}
    assert by_tag["essays"]["sources"] == 3 and by_tag["essays"]["gap"] is False
    assert by_tag["testing"]["sources"] == 1 and by_tag["testing"]["gap"] is True  # 0–1 = gap
    assert by_tag["financial-aid"]["sources"] == 0 and by_tag["financial-aid"]["gap"] is True
    # sorted by source count descending
    assert [r["tag"] for r in rows][0] == "essays"


def test_timeline_buckets_by_year_with_undated_last():
    tl = timeline([date(2025, 1, 1), date(2024, 6, 1), date(2025, 9, 1), None])
    assert tl == [{"period": "2024", "sources": 1}, {"period": "2025", "sources": 2},
                  {"period": "Undated", "sources": 1}]


def test_timeline_empty():
    assert timeline([]) == []


def test_consensus_ratio_of_themes_to_themes_plus_contradictions():
    insights = [{"kind": "theme"}, {"kind": "theme"}, {"kind": "theme"},
                {"kind": "contradiction"}, {"kind": "trend"}, {"kind": "gap"}]
    assert consensus(insights) == 75  # 3 / (3 + 1)


def test_consensus_is_100_when_themes_present_but_no_contradictions():
    assert consensus([{"kind": "theme"}, {"kind": "theme"}, {"kind": "gap"}]) == 100


def test_consensus_is_none_when_nothing_to_measure():
    # No themes and no contradictions → undefined, not a fabricated 100%.
    assert consensus([{"kind": "trend"}, {"kind": "gap"}]) is None
    assert consensus([]) is None


def test_prioritize_leads_with_contradictions_then_gaps_trends_themes():
    ins = [{"kind": "theme", "sources": [1]}, {"kind": "trend", "sources": [1]},
           {"kind": "gap", "sources": []}, {"kind": "contradiction", "sources": [1, 2]}]
    assert [i["kind"] for i in prioritize(ins)] == ["contradiction", "gap", "trend", "theme"]


def test_prioritize_breaks_ties_by_more_supporting_sources():
    ins = [{"kind": "theme", "sources": [1]}, {"kind": "theme", "sources": [1, 2, 3]}]
    assert prioritize(ins)[0]["sources"] == [1, 2, 3]


SMAP = {
    12: {"title": "Supplements podcast", "type": "youtube", "published_at": date(2025, 9, 15)},
    13: {"title": "Essays page", "type": "web", "published_at": None},
}


def test_check_filters_unknown_source_ids_and_builds_citations():
    out = InsightsOut(insights=[
        InsightOut(kind="theme", title="Be specific", detail="Name the seminar.",
                   tag="essays", source_ids=[12, 99, 12]),  # 99 unknown, 12 duplicated
    ])
    kept = check(out, SMAP, ["essays", "testing"])
    assert len(kept) == 1
    cites = kept[0]["sources"]
    assert [c["source_id"] for c in cites] == [12]  # deduped, unknown dropped
    assert cites[0]["app_link"] == "/sources/12"
    assert cites[0]["published_at"] == "2025-09-15"


def test_check_drops_non_gap_without_any_valid_source():
    out = InsightsOut(insights=[
        InsightOut(kind="theme", title="t", detail="d", source_ids=[99]),
        InsightOut(kind="trend", title="t", detail="d", source_ids=[]),
    ])
    assert check(out, SMAP, ["essays"]) == []


def test_check_keeps_gap_with_no_sources_but_requires_a_lens_tag():
    out = InsightsOut(insights=[
        InsightOut(kind="gap", title="Aid missing", detail="Barely covered.", tag="financial-aid", source_ids=[]),
        InsightOut(kind="gap", title="No tag", detail="d", tag=None, source_ids=[]),
        InsightOut(kind="gap", title="Bad tag", detail="d", tag="not-a-lens-tag", source_ids=[]),
    ])
    kept = check(out, SMAP, ["essays", "financial-aid"])
    assert len(kept) == 1
    assert kept[0]["tag"] == "financial-aid" and kept[0]["sources"] == []


def test_check_normalizes_tag_case_to_lens_vocabulary():
    out = InsightsOut(insights=[
        InsightOut(kind="theme", title="t", detail="d", tag="ESSAYS", source_ids=[13]),
    ])
    kept = check(out, SMAP, ["essays"])
    assert kept[0]["tag"] == "essays"
