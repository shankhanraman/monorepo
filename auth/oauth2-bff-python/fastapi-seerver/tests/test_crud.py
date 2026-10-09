import pytest
from fastapi.testclient import TestClient

from app.dependencies import current_user
from app.main import app

client = TestClient(app, headers={"X-CSRF": "1"})  # writes need the CSRF header (see test_auth.py)


@pytest.fixture(autouse=True)
def logged_in():
    # Token checks are covered in test_auth.py; here every request counts as logged in.
    app.dependency_overrides[current_user] = lambda: {"preferred_username": "tester"}
    yield
    app.dependency_overrides.pop(current_user, None)


def test_crud_lifecycle():
    # create
    alice = client.post("/api/users/", json={"username": "alice", "email": "alice@example.com"}).json()
    bob = client.post("/api/users/", json={"username": "bob", "email": "bob@example.com"}).json()
    p1 = client.post("/api/profiles/", json={"user_id": alice["id"], "bio": "hi"}).json()
    p2 = client.post("/api/profiles/", json={"user_id": bob["id"], "bio": "yo"}).json()
    assert client.post("/api/profiles/", json={"user_id": 999}).status_code == 404

    # read
    assert client.get(f"/api/users/{alice['id']}").json()["username"] == "alice"
    assert [p["id"] for p in client.get(f"/api/profiles/?user_id={alice['id']}").json()] == [p1["id"]]

    # update (full replace)
    r = client.put(f"/api/users/{alice['id']}", json={"username": "alice2", "email": "a2@example.com"})
    assert r.status_code == 200 and r.json() == {"id": alice["id"], "username": "alice2", "email": "a2@example.com"}
    r = client.put(f"/api/profiles/{p1['id']}", json={"user_id": alice["id"], "bio": "updated"})
    assert r.json()["bio"] == "updated"
    assert client.put("/api/users/999", json={"username": "x", "email": "x@example.com"}).status_code == 404
    assert client.put(f"/api/profiles/{p1['id']}", json={"user_id": 999}).status_code == 404  # unknown owner
    assert client.put("/api/profiles/999", json={"user_id": alice["id"]}).status_code == 404

    # delete user cascades to their profiles only
    assert client.delete(f"/api/users/{alice['id']}").status_code == 204
    assert client.get(f"/api/users/{alice['id']}").status_code == 404
    assert client.get(f"/api/profiles/{p1['id']}").status_code == 404
    assert client.get(f"/api/profiles/{p2['id']}").status_code == 200
    assert client.delete(f"/api/users/{alice['id']}").status_code == 404

    # delete profile
    assert client.delete(f"/api/profiles/{p2['id']}").status_code == 204
    assert client.delete(f"/api/profiles/{p2['id']}").status_code == 404

    # a new user never takes over an existing record
    carol = client.post("/api/users/", json={"username": "carol", "email": "carol@example.com"}).json()
    assert carol["id"] not in (alice["id"], bob["id"])
    assert client.get(f"/api/users/{bob['id']}").json()["username"] == "bob"


def test_unique_username_and_email():
    client.post("/api/users/", json={"username": "dana", "email": "dana@example.com"})
    erin = client.post("/api/users/", json={"username": "erin", "email": "erin@example.com"}).json()

    r = client.post("/api/users/", json={"username": "dana", "email": "other@example.com"})
    assert r.status_code == 409 and "unique" in r.json()["detail"]
    assert client.post("/api/users/", json={"username": "other", "email": "dana@example.com"}).status_code == 409
    assert client.put(f"/api/users/{erin['id']}", json={"username": "dana", "email": "erin@example.com"}).status_code == 409

    # the failed writes were rolled back; the API keeps working and nothing changed
    assert [u["username"] for u in client.get("/api/users/").json()] == ["dana", "erin"]
