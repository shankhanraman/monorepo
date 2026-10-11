"""Against the real Postgres (docker compose). Uses its own throwaway collections and cleans up.
No model calls: ingest jobs are not run, and segments are inserted directly."""
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

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
            conn.execute("DELETE FROM sources WHERE collection_id = %s", (slug,))
            conn.execute("DELETE FROM collections WHERE id = %s", (slug,))


@pytest.fixture
def api(config_dir, monkeypatch):
    monkeypatch.setattr(settings, "config_dir", config_dir)
    queued = []
    monkeypatch.setattr(jobs, "submit_ingest", queued.append)
    write(config_dir / "collections" / f"{A}.yaml", f"""\
        name: Test Yale
        lens: test-lens
        sources:
          - url: https://youtu.be/aaaaaaaaaaa
            label: Essays podcast
            priority: high
          - url: {YT}bbbbbbbbbbb
          - url: https://example.com/episode.mp3
    """)
    write(config_dir / "collections" / f"{B}.yaml", f"name: Test MIT\nlens: test-lens\nsources:\n  - url: {YT}ccccccccccc\n")
    cleanup()
    client = TestClient(app)  # no context manager → no startup job recovery
    client.queued = queued
    yield client
    cleanup()


def test_sync_is_idempotent_and_archives(api, config_dir):
    log = api.post(f"/sync?collection={A}").json()
    assert log["summary"] == {"queued": 2, "skipped": 0, "failed": 1, "archived": 0}
    assert len(api.queued) == 2
    assert api.post(f"/sync?collection={A}").json()["summary"] == {"queued": 0, "skipped": 2, "failed": 1, "archived": 0}

    write(config_dir / "collections" / f"{A}.yaml", f"name: Test Yale\nlens: test-lens\nsources:\n  - url: {YT}bbbbbbbbbbb\n")
    log = api.post(f"/sync?collection={A}").json()
    assert log["summary"]["archived"] == 1
    assert api.get(f"/collections/{A}/sync-log").json()["id"] == log["id"]
    sources = api.get(f"/collections/{A}/sources").json()
    assert [s["url"] for s in sources] == [f"{YT}bbbbbbbbbbb"]
    assert len(api.get(f"/collections/{A}/sources?include_archived=true").json()) == 2

    cols = {c["id"]: c for c in api.get("/collections").json()}
    assert cols[A]["source_counts"] == {"total": 1, "ready": 0, "in_progress": 1, "failed": 0, "archived": 1}
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
    assert api.get("/sources/999999999").status_code == 404

    bank = api.post(f"/collections/{A}/question-banks", json={"name": "B", "questions": [" Why major? ", "Why major?"]})
    assert bank.status_code == 201 and bank.json()["questions"] == ["Why major?"]
    assert api.get(f"/collections/{A}/question-banks").json()[0]["latest_run_id"] is None
    assert api.post(f"/collections/{A}/question-banks", json={"name": "B", "questions": []}).status_code == 422
    assert api.post("/question-banks/999999999/run").status_code == 404

    note = {"collection_id": A, "question": "q", "answer_md": "a [1]", "coverage": "strong", "citations": []}
    created = api.post("/notes", json=note)
    assert created.status_code == 201
    assert [n["id"] for n in api.get(f"/notes?collection={A}").json()] == [created.json()["id"]]
    assert api.delete(f"/notes/{created.json()['id']}").status_code == 204
    assert api.delete(f"/question-banks/{bank.json()['id']}").status_code == 204
    assert api.get("/health").json() == {"status": "ok"}
