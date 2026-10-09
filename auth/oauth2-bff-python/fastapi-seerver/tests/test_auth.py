"""BFF auth: session cookie + CSRF header on the API, and the OAuth 2.0 callback with Keycloak mocked."""

import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import SESSION_COOKIE
from app.main import app
from app.models.sessions import SessionRow
from app.routers.auth import TX_COOKIE, read_tx, sign_tx
from app.services import sessions

CSRF = {"X-CSRF": "1"}
USER = {"username": "a", "email": "a@example.com"}
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def signed_in_client(test_db, username="alice") -> TestClient:
    with test_db() as db:
        token = sessions.create_session(db, {"sub": "kc-1", "preferred_username": username, "email": f"{username}@example.com"},
                                        "refresh-1", ttl_hours=1)
    c = TestClient(app)
    c.cookies.set(SESSION_COOKIE, token)
    return c


def test_guest_reads_public_writes_401(test_db):
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/users/").status_code == 200
    assert c.get("/api/profiles/").status_code == 200
    assert c.get("/api/me").status_code == 401
    for method, path, body in [("post", "/api/users/", USER), ("put", "/api/users/1", USER), ("delete", "/api/users/1", None),
                               ("post", "/api/profiles/", {"user_id": 1}), ("put", "/api/profiles/1", {"user_id": 1}),
                               ("delete", "/api/profiles/1", None)]:
        r = c.request(method, path, json=body, headers=CSRF)
        assert r.status_code == 401, (method, path, r.status_code)


def test_session_cookie_and_csrf(test_db):
    c = signed_in_client(test_db)
    assert c.get("/api/me").json() == {"username": "alice", "email": "alice@example.com"}
    assert c.post("/api/users/", json=USER).status_code == 403  # cookie alone isn't enough for a write
    assert c.post("/api/users/", json=USER, headers={"X-CSRF": "0"}).status_code == 403
    assert c.post("/api/users/", json=USER, headers=CSRF).status_code == 201

    forged = TestClient(app)
    forged.cookies.set(SESSION_COOKIE, "not-a-real-session")
    assert forged.get("/api/me").status_code == 401


def test_expired_session_is_rejected(test_db):
    c = signed_in_client(test_db)
    with test_db() as db:
        for row in db.query(SessionRow):
            row.expires_at -= timedelta(hours=2)
        db.commit()
    assert c.get("/api/me").status_code == 401


def test_logout_deletes_session_and_ends_keycloak_session(test_db):
    c = signed_in_client(test_db)
    old_cookie = c.cookies.get(SESSION_COOKIE)
    assert c.post("/auth/logout").status_code == 403  # logout is CSRF-protected too
    with patch("app.routers.auth.httpx.post") as kc:
        r = c.post("/auth/logout", headers=CSRF)
    assert r.status_code == 204
    assert 'bff_session=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]
    assert kc.call_args.args[0].endswith("/protocol/openid-connect/logout")
    assert kc.call_args.kwargs["data"]["refresh_token"] == "refresh-1"  # back-channel, never via the browser

    replay = TestClient(app)
    replay.cookies.set(SESSION_COOKIE, old_cookie)
    assert replay.get("/api/me").status_code == 401  # the old cookie is dead server-side


def test_tx_cookie_is_tamper_proof():
    value = sign_tx({"state": "s", "nonce": "n", "verifier": "v", "next": "/"})
    assert read_tx(value)["state"] == "s"
    payload, _, sig = value.partition(".")
    assert read_tx(payload + "." + sig[:-2] + "AA") is None
    assert read_tx("garbage") is None and read_tx("") is None


def start_login(c: TestClient, next_path="/after") -> tuple[str, dict]:
    r = c.get(f"/auth/login?next={next_path}", follow_redirects=False)
    assert r.status_code == 302
    assert "httponly" in r.headers["set-cookie"].lower()
    url = urlparse(r.headers["location"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.path.endswith("/protocol/openid-connect/auth")
    assert q["client_id"] == settings["OIDC_CLIENT_ID"] and q["code_challenge_method"] == "S256"
    return q["state"], read_tx(c.cookies.get(TX_COOKIE))


def keycloak_tokens(nonce: str, **overrides) -> httpx.Response:
    claims = {"iss": settings["KEYCLOAK_ISSUER"], "aud": settings["OIDC_CLIENT_ID"], "sub": "kc-42",
              "preferred_username": "alice", "email": "alice@example.com", "nonce": nonce,
              "iat": int(time.time()), "exp": int(time.time()) + 300} | overrides
    id_token = jwt.encode(claims, key, algorithm="RS256")
    return httpx.Response(200, json={"id_token": id_token, "access_token": "ACCESS-TOKEN-x9", "refresh_token": "REFRESH-TOKEN-x9"})


class FakeSigningKey:
    key = key.public_key()


@patch("app.routers.auth.jwks_client.get_signing_key_from_jwt", return_value=FakeSigningKey)
def test_callback_creates_session(_, test_db):
    c = TestClient(app)
    state, tx = start_login(c)
    with patch("app.routers.auth.httpx.post", return_value=keycloak_tokens(tx["nonce"])) as kc:
        r = c.get(f"/auth/callback?code=the-code&state={state}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/after"
    sent = kc.call_args.kwargs["data"]
    assert sent["code"] == "the-code" and sent["code_verifier"] == tx["verifier"] and "client_secret" in sent
    session_cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE)][0]
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    browser_sees = r.text + str(r.headers)  # body, Location and every Set-Cookie
    assert "TOKEN-x9" not in browser_sees and kc.return_value.json()["id_token"] not in browser_sees  # no token leaks
    assert c.get("/api/me").json()["username"] == "alice"


@patch("app.routers.auth.jwks_client.get_signing_key_from_jwt", return_value=FakeSigningKey)
def test_callback_rejects_bad_logins(_, test_db):
    c = TestClient(app)
    state, tx = start_login(c)
    assert c.get("/auth/callback?code=x&state=wrong", follow_redirects=False).status_code == 400

    with patch("app.routers.auth.httpx.post", return_value=keycloak_tokens("other-nonce")):
        assert c.get(f"/auth/callback?code=x&state={state}", follow_redirects=False).status_code == 400
    with patch("app.routers.auth.httpx.post", return_value=keycloak_tokens(tx["nonce"], aud="someone-else")):
        assert c.get(f"/auth/callback?code=x&state={state}", follow_redirects=False).status_code == 400
    with patch("app.routers.auth.httpx.post", return_value=httpx.Response(400, json={"error": "invalid_grant"})):
        assert c.get(f"/auth/callback?code=x&state={state}", follow_redirects=False).status_code == 400

    fresh = TestClient(app)  # no tx cookie at all
    assert fresh.get(f"/auth/callback?code=x&state={state}", follow_redirects=False).status_code == 400
    assert c.get("/api/me").status_code == 401  # none of the above signed anyone in


def test_open_redirect_is_blocked():
    for evil in ["https://evil.example", "//evil.example", "/\\evil.example"]:
        c = TestClient(app)
        c.get("/auth/login", params={"next": evil}, follow_redirects=False)
        assert read_tx(c.cookies.get(TX_COOKIE))["next"] == "/"
