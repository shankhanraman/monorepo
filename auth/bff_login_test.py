#!/usr/bin/env python3
"""Drive the OAuth 2.0 BFF login end-to-end (no browser) and test session + CSRF enforcement.

Flow (the backend is the confidential OAuth client; the browser only ever gets an
HttpOnly session cookie):
  GET  /auth/login            -> 302 to Keycloak authorize (sets signed bff_tx cookie)
  GET  Keycloak authorize     -> login page
  POST Keycloak authenticate  -> 302 to APP_URL/auth/callback?code&state
  GET  /auth/callback         -> back-channel code exchange + ID-token verify,
                                 Set-Cookie bff_session (HttpOnly), 302 to app
Then probe /api/me and a protected write with/without session and X-CSRF.

The registered redirect_uri is :5175 (Vite). We drive FastAPI directly on :8002 and
rewrite the callback port — cookies are host-scoped (localhost), so bff_tx carries,
and redirect_uri stays :5175 end-to-end so Keycloak stays satisfied. No Vite needed.
"""
import re, sys, requests

API = "http://localhost:8002"          # FastAPI directly
APP_ORIGIN = "http://localhost:5175"   # registered redirect origin (Vite); never actually contacted
ISSUER = "http://localhost:8082/realms/bff-lab"
USER, PW = "alice", "alice123"

def login_session():
    s = requests.Session()
    # 1. Start login on the backend -> 302 to Keycloak authorize
    r = s.get(f"{API}/auth/login", allow_redirects=False)
    assert r.status_code == 302, f"/auth/login -> {r.status_code}"
    kc_auth = r.headers["Location"]
    assert "bff_tx" in s.cookies, "backend did not set bff_tx transaction cookie"
    # 2. Fetch Keycloak login page
    r = s.get(kc_auth)
    r.raise_for_status()
    for c in s.cookies:            # Keycloak marks AUTH_SESSION_ID Secure; drop it for localhost http
        c.secure = False
    m = re.search(r'id="kc-form-login"[^>]+action="([^"]+)"', r.text) or re.search(r'action="([^"]+)"', r.text)
    action = m.group(1).replace("&amp;", "&")
    # 3. Submit credentials -> 302 to APP_ORIGIN/auth/callback?code&state
    r = s.post(action, data={"username": USER, "password": PW, "credentialId": ""}, allow_redirects=False)
    assert r.status_code in (301,302,303,307), f"login not redirected: {r.status_code}"
    cb = r.headers["Location"]
    assert cb.startswith(APP_ORIGIN + "/auth/callback"), f"unexpected callback: {cb}"
    # 4. Fetch the callback on the backend (rewrite port 5175 -> 8002)
    cb_backend = cb.replace(APP_ORIGIN, API)
    r = s.get(cb_backend, allow_redirects=False)
    assert r.status_code == 302, f"/auth/callback -> {r.status_code}: {r.text[:200]}"
    assert "bff_session" in s.cookies, "no bff_session cookie after callback"
    return s

def probe(s, method, path, csrf=False, body=None, use_session=True):
    headers = {"X-CSRF": "1"} if csrf else {}
    cookies = None if use_session else {}
    r = requests.request(method, API + path, headers=headers, json=body,
                         cookies=(s.cookies if use_session else {}), timeout=10)
    return r.status_code, r.text[:160]

def main():
    print("=== 1. Guest (no session): GET /api/me ===")
    r = requests.get(API + "/api/me"); print("   HTTP", r.status_code, "(expect 401)", "|", r.text[:80])

    print("\n=== 2. Guest read: GET /api/users/ ===")
    r = requests.get(API + "/api/users/"); print("   HTTP", r.status_code, "(expect 200)")

    print("\n=== 3. Write with NO session: POST /api/users/ (X-CSRF set) ===")
    r = requests.post(API + "/api/users/", headers={"X-CSRF":"1"}, json={"username":"bff_x","email":"bff.x@example.com"})
    print("   HTTP", r.status_code, "(expect 401)", "|", r.text[:80])

    print("\n=== 4. Driving BFF OAuth login as", USER, "===")
    s = login_session()
    print("   OK  bff_session cookie set:", s.cookies.get("bff_session")[:16] + "...")

    print("\n=== 5. GET /api/me WITH session ===")
    r = requests.get(API + "/api/me", cookies=s.cookies); print("   HTTP", r.status_code, "(expect 200)", "|", r.text[:120])

    print("\n=== 6. Write WITH session but NO X-CSRF: POST /api/users/ ===")
    sc, b = probe(s, "POST", "/api/users/", csrf=False, body={"username":"bff_nocsrf","email":"bff.nocsrf@example.com"})
    print("   HTTP", sc, "(expect 403)", "|", b[:100])

    print("\n=== 7. Write WITH session AND X-CSRF: POST /api/users/ ===")
    sc, b = probe(s, "POST", "/api/users/", csrf=True, body={"username":"bff_alice","email":"bff.alice@example.com"})
    print("   HTTP", sc, "(expect 200/201)", "|", b[:160])

if __name__ == "__main__":
    main()
