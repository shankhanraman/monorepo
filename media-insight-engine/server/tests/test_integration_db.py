"""Against the real Postgres (docker compose). Uses its own throwaway collections and cleans up.
No model calls: ingest jobs are not run, and segments are inserted directly."""
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.config import settings
from tests.conftest import write

try:
    psycopg.connect(settings.database_url, connect_timeout=2).close()
except Exception:
    pytest.skip("database not reachable (run inside docker compose)", allow_module_level=True)

from app.db import pool  # noqa: E402
from app.main import app  # noqa: E402
from app.services import embed, jobs  # noqa: E402
from app.services.retrieve import retrieve  # noqa: E402

A, B = "zz-test-yale", "zz-test-mit"
YT = "https://www.youtube.com/watch?v="


def cleanup():
    with pool().connection() as conn:
        for slug in (A, B):
            conn.execute("DELETE FROM notes WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM answers WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM question_banks WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM sync_logs WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM collection_analyses WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM sources WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM collections WHERE id = %s", (slug,))


@pytest.fixture
def api(config_dir, monkeypatch):
    monkeypatch.setattr(settings, "config_dir", config_dir)
    queued = []
    monkeypatch.setattr(jobs, "submit_ingest", lambda source_id, source_type=None: queued.append((source_id, source_type)))
    synths = []
    monkeypatch.setattr(jobs, "submit_synthesis", lambda collection_id: synths.append(collection_id))
    write(config_dir / "collections" / f"{A}.yaml", f"""\
        name: Test Yale
        lens: test-lens
        sources:
          - url: https://youtu.be/aaaaaaaaaaa
            label: Essays podcast
            priority: high
          - url: {YT}bbbbbbbbbbb
          - url: https://example.com/episode.mp3
          - url: https://open.spotify.com/episode/abc
    """)
    write(config_dir / "collections" / f"{B}.yaml", f"name: Test MIT\nlens: test-lens\nsources:\n  - url: {YT}ccccccccccc\n")
    cleanup()
    client = TestClient(app)  # no context manager → no startup job recovery
    client.queued = queued
    client.synths = synths
    yield client
    cleanup()


def test_sync_is_idempotent_and_archives(api, config_dir):
    log = api.post(f"/sync?collection={A}").json()
    assert log["summary"] == {"queued": 3, "skipped": 0, "failed": 1, "archived": 0}
    assert sorted(t for _, t in api.queued) == ["audio", "youtube", "youtube"]   # audio goes to its own pool
    assert api.post(f"/sync?collection={A}").json()["summary"] == {"queued": 0, "skipped": 3, "failed": 1, "archived": 0}

    write(config_dir / "collections" / f"{A}.yaml", f"name: Test Yale\nlens: test-lens\nsources:\n  - url: {YT}bbbbbbbbbbb\n")
    log = api.post(f"/sync?collection={A}").json()
    assert log["summary"]["archived"] == 2
    assert api.get(f"/collections/{A}/sync-log").json()["id"] == log["id"]
    sources = api.get(f"/collections/{A}/sources").json()
    assert [s["url"] for s in sources] == [f"{YT}bbbbbbbbbbb"]
    assert len(api.get(f"/collections/{A}/sources?include_archived=true").json()) == 3

    cols = {c["id"]: c for c in api.get("/collections").json()}
    assert cols[A]["source_counts"] == {"total": 1, "ready": 0, "in_progress": 1, "failed": 0, "archived": 2}
    assert api.post("/sync?collection=nope").status_code == 404
    write(config_dir / "collections" / f"{A}.yaml", "name: Broken\nlens: missing-lens\n")
    assert api.post(f"/sync?collection={A}").status_code == 422


def make_ready(slug: str, text: str) -> int:
    """Pretend ingest finished: one ready source with one embedded segment."""
    with pool().connection() as conn:
        src = conn.execute("SELECT id FROM sources WHERE collection_id = %s ORDER BY id LIMIT 1", (slug,)).fetchone()["id"]
        conn.execute("UPDATE sources SET status = 'ready', title = %s, published_at = '2026-01-01' WHERE id = %s",
                     (f"{slug} video", src))
        conn.execute("INSERT INTO segments (source_id, ord, start_s, end_s, text, summary, tags, embedding) "
                     "VALUES (%s, 0, 720, 780, %s, %s, '{essays}', %s)", (src, text, text, embed.passages([text])[0]))
    return src


def test_retrieval_is_isolated_per_collection(api):
    api.post(f"/sync?collection={A}")
    api.post(f"/sync?collection={B}")
    make_ready(A, "Yale officers want to know why you chose your major and what made you curious.")
    make_ready(B, "MIT wants makers: tell us why you love building things and your intended major.")
    q = "why this major essay"
    assert {h["collection_id"] for h in retrieve(A, q)} == {A}                    # AC-10
    assert {h["collection_id"] for h in retrieve(B, q)} == {B}
    assert {A, B} <= {h["collection_id"] for h in retrieve("all", q, {}, k=50)}
    assert retrieve(A, q, {"tags": ["testing"]}) == []
    assert retrieve(A, "SAT", {"date_from": "2026-06-01"}) == []
    assert retrieve(A, "curious major")[0]["start_s"] == 720


def test_source_detail_banks_and_notes(api):
    api.post(f"/sync?collection={A}")
    src = make_ready(A, "Officers want curiosity.")
    detail = api.get(f"/sources/{src}").json()
    assert detail["segments"][0]["deep_link"] == "https://youtu.be/aaaaaaaaaaa?t=720"
    assert (detail["stale"], detail["progress"], detail["media_url"]) == (False, None, None)  # published 2026-01-01
    undated = [s for s in api.get(f"/collections/{A}/sources").json() if s["id"] != src]
    assert undated and all(s["stale"] for s in undated)                                    # no date → stale
    assert api.get("/sources/999999999").status_code == 404

    bank = api.post(f"/collections/{A}/question-banks", json={"name": "B", "questions": [" Why major? ", "Why major?"]})
    assert bank.status_code == 201 and bank.json()["questions"] == ["Why major?"]
    assert api.get(f"/collections/{A}/question-banks").json()[0]["latest_run_id"] is None
    assert api.post(f"/collections/{A}/question-banks", json={"name": "B", "questions": []}).status_code == 422
    assert api.post("/question-banks/999999999/run").status_code == 404

    # A finished run (inserted directly: no model calls) exports as Markdown and PDF.
    with pool().connection() as conn:
        run_id = conn.execute("INSERT INTO bank_runs (bank_id, status, done, total, finished_at) "
                              "VALUES (%s, 'done', 1, 1, now()) RETURNING id", (bank.json()["id"],)).fetchone()["id"]
        conn.execute("INSERT INTO answers (collection_id, run_id, item_index, question, status, answer_md, coverage) "
                     "VALUES (%s, %s, 0, 'Why major?', 'done', 'Be specific.', 'partial')", (A, run_id))
    assert "## 1. Why major?" in api.get(f"/bank-runs/{run_id}/report.md").text
    pdf = api.get(f"/bank-runs/{run_id}/report.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"

    note = {"collection_id": A, "question": "q", "answer_md": "a [1]", "coverage": "strong", "citations": []}
    created = api.post("/notes", json=note)
    assert created.status_code == 201
    assert [n["id"] for n in api.get(f"/notes?collection={A}").json()] == [created.json()["id"]]
    assert api.delete(f"/notes/{created.json()['id']}").status_code == 204
    assert api.delete(f"/question-banks/{bank.json()['id']}").status_code == 204
    assert api.get("/health").json() == {"status": "ok"}


def test_insights_empty_then_persisted_roundtrip(api):
    api.post(f"/sync?collection={A}")
    empty = api.get(f"/collections/{A}/insights").json()                       # never analyzed yet
    assert empty["status"] == "empty" and empty["insights"] == [] and empty["coverage"] == []
    assert (empty["source_count"], empty["consensus"], empty["stale"]) == (0, None, False)
    assert api.get("/collections/zz-nope/insights").status_code == 404

    # Persist an analysis directly (no model call), with an old generated_at so the later sync marks it stale.
    insights = [{"kind": "theme", "title": "Be specific", "detail": "Name the seminar.", "tag": "essays",
                 "sources": [{"source_id": 1, "source_title": "Essays podcast", "source_type": "youtube",
                              "published_at": "2025-09-15", "app_link": "/sources/1"}]}]
    cov = [{"tag": "essays", "sources": 3, "gap": False}, {"tag": "testing", "sources": 0, "gap": True}]
    tl = [{"period": "2025", "sources": 3}]
    with pool().connection() as conn:
        conn.execute(
            """INSERT INTO collection_analyses (collection_id, status, model, source_count, segment_count,
                 consensus, insights, coverage, timeline, generated_at)
               VALUES (%s, 'ready', 'claude', 3, 30, 72, %s, %s, %s, '2020-01-01')""",
            (A, Jsonb(insights), Jsonb(cov), Jsonb(tl)))
    got = api.get(f"/collections/{A}/insights").json()
    assert got["status"] == "ready" and got["consensus"] == 72 and got["source_count"] == 3
    assert got["insights"][0]["sources"][0]["app_link"] == "/sources/1"
    assert [c["gap"] for c in got["coverage"]] == [False, True]
    assert got["stale"] is True   # the sync above set last_synced_at (now) > generated_at (2020)


def test_resync_without_queue_triggers_synthesis(api):
    api.post(f"/sync?collection={A}")           # 3 queued → ingest will drain and trigger; no direct trigger
    assert api.synths == []
    api.post(f"/sync?collection={A}")           # all skipped, nothing queued → trigger directly
    assert api.synths == [A]
