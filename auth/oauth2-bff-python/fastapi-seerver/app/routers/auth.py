"""OAuth 2.0 authorization-code flow (+ PKCE), with this backend as the confidential client.

Browser                      FastAPI (this file)                         Keycloak
  GET /auth/login  ───────►  state, nonce, PKCE → signed bff_tx cookie
                   ◄───────  302 to Keycloak /auth  ──────────────────►  login page
  ...user signs in on Keycloak...                                   ◄──  302 /auth/callback?code&state
  GET /auth/callback ─────►  check state, POST /token (secret + verifier) ──►
                             verify ID token (signature, iss, aud, nonce)  ◄── tokens
                   ◄───────  Set-Cookie bff_session (HttpOnly), 302 to the app
Tokens stay here. The browser only ever gets the opaque session cookie.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import oidc_url, settings
from app.db import get_db
from app.dependencies import SESSION_COOKIE, csrf_header
from app.services import sessions

router = APIRouter(prefix="/auth", tags=["auth"])

TX_COOKIE = "bff_tx"
TX_SECONDS = 600  # a login must finish within 10 minutes

# Keycloak's public signing keys, to verify the ID token. Fetched lazily, cached.
jwks_client = jwt.PyJWKClient(oidc_url("certs"))


# --- small helpers -------------------------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_tx(data: dict) -> str:
    """Tamper-proof cookie value: base64(json) + "." + HMAC-SHA256. Not encrypted (holds nothing secret to the user)."""
    payload = _b64(json.dumps({**data, "exp": int(time.time()) + TX_SECONDS}).encode())
    sig = _b64(hmac.new(settings["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_tx(value: str) -> dict | None:
    """The login transaction from the cookie, or None if missing, tampered with or expired."""
    payload, _, sig = value.partition(".")
    good = _b64(hmac.new(settings["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256).digest())
    if not payload or not hmac.compare_digest(sig, good):
        return None
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return data if data["exp"] > time.time() else None


def safe_next(path: str) -> str:
    """Only same-site relative paths, so /auth/login?next=https://evil.example can't bounce users away."""
    return path if path.startswith("/") and not path.startswith("//") and "\\" not in path else "/"


def _redirect_uri() -> str:
    return f"{settings['APP_URL']}/auth/callback"


def _set_cookie(response: Response, name: str, value: str, max_age: int, path: str) -> None:
    response.set_cookie(name, value, max_age=max_age, path=path, httponly=True, samesite="lax",
                        secure=settings["COOKIE_SECURE"])


# --- routes --------------------------------------------------------------------------------------

def _start(endpoint: str, next_path: str) -> RedirectResponse:
    """Begin a login (endpoint "auth") or a sign-up (endpoint "registrations") at Keycloak."""
    state, nonce, verifier = secrets.token_urlsafe(16), secrets.token_urlsafe(16), secrets.token_urlsafe(48)
    query = urlencode({
        "client_id": settings["OIDC_CLIENT_ID"],
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": _redirect_uri(),
        "state": state,  # CSRF protection for the callback
        "nonce": nonce,  # binds the ID token to this login
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),  # PKCE
        "code_challenge_method": "S256",
    })
    response = RedirectResponse(f"{oidc_url(endpoint)}?{query}", status_code=302)
    tx = sign_tx({"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next_path)})
    _set_cookie(response, TX_COOKIE, tx, TX_SECONDS, path="/auth")
    return response


@router.get("/login")
def login(next: str = "/"):
    return _start("auth", next)


@router.get("/register")
def register(next: str = "/"):
    return _start("registrations", next)


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             db: Session = Depends(get_db)):
    if error:  # e.g. the user cancelled on Keycloak's page
        raise HTTPException(400, f"Login failed: {error}")
    tx = read_tx(request.cookies.get(TX_COOKIE, ""))
    if tx is None or not state or not hmac.compare_digest(state, tx["state"]) or not code:
        raise HTTPException(400, "Invalid or expired login, please try again")

    # Back-channel: exchange the code for tokens. Only this server knows the client secret and the PKCE verifier.
    r = httpx.post(oidc_url("token"), timeout=10, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(),
        "client_id": settings["OIDC_CLIENT_ID"],
        "client_secret": settings["OIDC_CLIENT_SECRET"],
        "code_verifier": tx["verifier"],
    })
    if r.status_code != 200:
        raise HTTPException(400, "Code exchange with Keycloak failed")
    tokens = r.json()

    # Verify the ID token: who logged in, issued by our Keycloak, for this client, for this very login.
    try:
        claims = jwt.decode(
            tokens["id_token"],
            jwks_client.get_signing_key_from_jwt(tokens["id_token"]).key,
            algorithms=["RS256"],
            audience=settings["OIDC_CLIENT_ID"],
            issuer=settings["KEYCLOAK_ISSUER"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except (KeyError, jwt.PyJWTError) as e:
        raise HTTPException(400, f"Invalid ID token: {e}")
    if not hmac.compare_digest(str(claims.get("nonce", "")), tx["nonce"]):
        raise HTTPException(400, "ID token nonce mismatch")

    token = sessions.create_session(db, claims, tokens.get("refresh_token"), settings["SESSION_TTL_HOURS"])
    response = RedirectResponse(tx["next"], status_code=302)
    _set_cookie(response, SESSION_COOKIE, token, settings["SESSION_TTL_HOURS"] * 3600, path="/")
    response.delete_cookie(TX_COOKIE, path="/auth")
    return response


@router.post("/logout", status_code=204, dependencies=[Depends(csrf_header)])
def logout(request: Request, db: Session = Depends(get_db)):
    """End the app session, then the Keycloak session (server-to-server, so no token goes to the browser)."""
    token = request.cookies.get(SESSION_COOKIE)
    row = sessions.delete_session(db, token) if token else None
    if row is not None and row.refresh_token:
        try:
            httpx.post(oidc_url("logout"), timeout=10, data={
                "client_id": settings["OIDC_CLIENT_ID"],
                "client_secret": settings["OIDC_CLIENT_SECRET"],
                "refresh_token": row.refresh_token,
            })
        except httpx.HTTPError:
            pass  # app session is already gone; Keycloak's ends on its own idle timeout
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
