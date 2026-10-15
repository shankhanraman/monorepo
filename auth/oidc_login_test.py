#!/usr/bin/env python3
"""Drive a real Keycloak Authorization-Code + PKCE login (no browser) and test a
FastAPI resource server's JWT enforcement.

Replicates exactly what the SPA does: hit the authorize endpoint, submit the
Keycloak login form, capture the redirect code, exchange it (with PKCE verifier)
for an access token. Then probes a protected endpoint four ways.

Uses requests.Session so the Keycloak auth-session cookies are carried across the
GET (login page) -> POST (credentials) -> redirect automatically.
"""
import argparse, base64, hashlib, json, re, os, secrets, sys
import requests

def b64url(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def get_token(issuer, client, redirect, user, password):
    s = requests.Session()
    verifier = b64url(os.urandom(40))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(12)
    # 1. GET authorize -> login page HTML (+ sets AUTH_SESSION_ID / KC_RESTART cookies on the session)
    r = s.get(issuer + "/protocol/openid-connect/auth", params={
        "client_id": client, "response_type": "code", "redirect_uri": redirect,
        "scope": "openid", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    r.raise_for_status()
    # Keycloak marks AUTH_SESSION_ID 'Secure'. Browsers send it on http://localhost (secure context);
    # requests won't over plain HTTP. On trusted localhost, drop Secure so the auth session is carried.
    for c in s.cookies:
        c.secure = False
    m = re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', r.text) or re.search(r'action="([^"]+)"', r.text)
    if not m:
        print("ERROR: no login form in page:\n", r.text[:500]); sys.exit(2)
    action = m.group(1).replace("&amp;", "&")
    # 2. POST credentials -> 302 to redirect_uri?code=... (do NOT follow: redirect_uri has no live server)
    r2 = s.post(action, data={"username": user, "password": password, "credentialId": ""},
                allow_redirects=False)
    if r2.status_code not in (301, 302, 303, 307):
        err = re.search(r'id="input-error[^"]*"[^>]*>\s*([^<]+)', r2.text) or \
              re.search(r'kc-feedback-text"?>\s*([^<]+)', r2.text)
        print(f"ERROR: login not redirected (HTTP {r2.status_code}).",
              "Keycloak:", err.group(1).strip() if err else "(no feedback text found)")
        sys.exit(3)
    loc = r2.headers["Location"]
    code = requests.utils.urlparse(loc).query
    code = dict(p.split("=", 1) for p in code.split("&") if "=" in p).get("code")
    if not code:
        print("ERROR: no code in redirect:", loc); sys.exit(4)
    # 3. Exchange code + PKCE verifier for tokens
    rt = s.post(issuer + "/protocol/openid-connect/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
        "client_id": client, "code_verifier": verifier,
    })
    rt.raise_for_status()
    return rt.json()["access_token"]

def probe(api, path, method="GET", token=None, body=None):
    url = api.rstrip("/") + path
    headers = {}
    if token: headers["Authorization"] = "Bearer " + token
    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=10)
        return r.status_code, r.text[:300]
    except requests.RequestException as e:
        return None, str(e)

def main():
    ap = argparse.ArgumentParser()
    for n in ("issuer","client","redirect","user","password","api","read","write"):
        ap.add_argument("--"+n, required=True)
    ap.add_argument("--write-json", default='{"name":"pkce-test","email":"pkce@test.local"}')
    a = ap.parse_args()
    wbody = json.loads(a.write_json)

    print("=== 1. Driving Keycloak auth-code + PKCE login as", a.user, "===")
    token = get_token(a.issuer, a.client, a.redirect, a.user, a.password)
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    print("  OK  access_token claims: iss=%s | aud=%s | preferred_username=%s | typ=%s" % (
        claims.get("iss"), claims.get("aud"), claims.get("preferred_username"), claims.get("typ")))

    print("\n=== 2. Public read, NO token ->", a.read)
    s, _ = probe(a.api, a.read); print("   HTTP", s, " (expect 200)")

    print("\n=== 3. Protected write, NO token ->", a.write)
    s, b = probe(a.api, a.write, "POST", token=None, body=wbody); print("   HTTP", s, " (expect 401/403) |", b[:100])

    print("\n=== 4. Protected write, TAMPERED token ->", a.write)
    bad = token[:-3] + ("aaa" if token[-3:] != "aaa" else "bbb")
    s, b = probe(a.api, a.write, "POST", token=bad, body=wbody); print("   HTTP", s, " (expect 401) |", b[:100])

    print("\n=== 5. Protected write, VALID token ->", a.write)
    s, b = probe(a.api, a.write, "POST", token=token, body=wbody); print("   HTTP", s, " (expect 200/201) |", b[:200])

if __name__ == "__main__":
    main()
