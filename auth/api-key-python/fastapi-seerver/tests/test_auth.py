from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.apikeys import ApiKeyRow, hash_key

client = TestClient(app)

GOOD = "test-good-key"
BAD = "test-bad-key"
REVOKED = "test-revoked-key"


def _seed_keys():
    # conftest overrides get_db with a fresh in-memory SQLite session; insert our test keys there.
    db = next(app.dependency_overrides[get_db]())
    db.add(ApiKeyRow(name="good", prefix=GOOD[:6], key_hash=hash_key(GOOD), active=True))
    db.add(ApiKeyRow(name="revoked", prefix=REVOKED[:6], key_hash=hash_key(REVOKED), active=False))
    db.commit()


def test_auth():
    _seed_keys()
    assert client.get("/health").status_code == 200

    # Reads are public.
    assert client.get("/users/").status_code == 200
    assert client.get("/profiles/").status_code == 200

    user = {"username": "a", "email": "a@example.com"}
    # Writes need a valid, active key.
    assert client.post("/users/", json=user).status_code == 401                                    # no key
    assert client.post("/users/", json=user, headers={"X-API-Key": BAD}).status_code == 401         # unknown key
    assert client.post("/users/", json=user, headers={"X-API-Key": REVOKED}).status_code == 401     # revoked key
    assert client.post("/users/", json=user, headers={"X-API-Key": GOOD}).status_code == 201        # valid key

    # Every write verb is gated.
    assert client.put("/users/1", json=user, headers={"X-API-Key": BAD}).status_code == 401
    assert client.delete("/users/1").status_code == 401
    assert client.post("/profiles/", json={"user_id": 1}).status_code == 401

    # /me echoes which key was accepted, never the secret (no hash in the response).
    me = client.get("/me", headers={"X-API-Key": GOOD})
    assert me.status_code == 200 and me.json()["name"] == "good"
    assert "key_hash" not in me.json()
    assert client.get("/me").status_code == 401
