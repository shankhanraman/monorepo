"""The app trusts only the sidecar's XFCC header. Tests set it directly (no Docker, no certificates)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def as_(name: str) -> dict:
    # What Envoy sends after a successful mTLS handshake (By = the sidecar's own identity).
    return {"x-forwarded-client-cert": f"By=spiffe://lab.local/users;Hash=abc123;URI=spiffe://lab.local/{name}"}


def test_identity_is_required():
    assert client.get("/users/").status_code == 401  # no header = didn't come through the sidecar
    assert client.get("/users/", headers={"x-forwarded-client-cert": "Hash=abc"}).status_code == 401
    assert client.get("/users/", headers={"x-forwarded-client-cert": "URI=spiffe://evil.example/admin"}).status_code == 401


def test_whoami_and_parsing():
    r = client.get("/whoami", headers=as_("reporting"))
    assert r.json() == {"service": "users", "caller": "reporting", "cert_sha256": "abc123"}
    quoted = {"x-forwarded-client-cert": 'By=spiffe://lab.local/users;Hash=h;URI="spiffe://lab.local/admin"'}
    assert client.get("/whoami", headers=quoted).json()["caller"] == "admin"


def test_authorization_by_caller():
    new = {"username": "carol", "email": "carol@example.com"}
    assert client.post("/users/", json=new, headers=as_("reporting")).status_code == 403  # authenticated, not allowed
    assert client.post("/users/", json=new, headers=as_("orders")).status_code == 403
    r = client.post("/users/", json=new, headers=as_("admin"))
    assert r.status_code == 201 and r.json()["created_by"] == "admin"
    uid = r.json()["id"]
    for reader in ("orders", "admin", "reporting"):
        assert client.get(f"/users/{uid}", headers=as_(reader)).status_code == 200
    assert client.get(f"/users/{uid}", headers=as_("stranger")).status_code == 403
    assert client.get("/users/999", headers=as_("orders")).status_code == 404
