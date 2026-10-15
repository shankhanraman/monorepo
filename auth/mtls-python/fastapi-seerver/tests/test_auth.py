from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# nginx sets these headers after verifying the client cert; here we send them directly to the app.
OK = {"X-SSL-Client-Verify": "SUCCESS", "X-SSL-Client-DN": "CN=alice"}
FAILED = {"X-SSL-Client-Verify": "FAILED:certificate has expired", "X-SSL-Client-DN": "CN=alice"}
NONE = {"X-SSL-Client-Verify": "NONE"}


def test_auth():
    assert client.get("/health").status_code == 200

    # Reads are public (no client cert needed).
    assert client.get("/users/").status_code == 200
    assert client.get("/profiles/").status_code == 200

    user = {"username": "a", "email": "a@example.com"}
    # Writes need a verified client cert.
    assert client.post("/users/", json=user).status_code == 401                       # no cert at all
    assert client.post("/users/", json=user, headers=NONE).status_code == 401          # TLS saw no cert
    assert client.post("/users/", json=user, headers=FAILED).status_code == 401        # cert failed verification
    assert client.post("/users/", json=user, headers=OK).status_code == 201            # verified cert

    # Every write verb is gated.
    assert client.put("/users/1", json=user, headers=NONE).status_code == 401
    assert client.delete("/users/1").status_code == 401
    assert client.post("/profiles/", json={"user_id": 1}).status_code == 401

    # /me echoes the client cert's CN.
    me = client.get("/me", headers=OK)
    assert me.status_code == 200 and me.json()["cn"] == "alice"
    assert client.get("/me").status_code == 401
