#!/usr/bin/env python3
"""Drive the full SAML 2.0 SP-initiated SSO against the saml-python lab (no browser) and test the
session the SP issues.

Flow:
  GET  /saml/login            -> 302 to Keycloak SAML SSO (carries the AuthnRequest)
  GET  Keycloak SSO URL       -> login page
  POST Keycloak authenticate  -> 200 with an auto-submit form POSTing SAMLResponse to /saml/acs
  POST /saml/acs              -> SP verifies the signed assertion, sets saml_session cookie, 302s
Then: write with the session (201), /me (the NameID), write without it (401).
"""
import html
import re
import sys

import requests

SP = "http://localhost:8006"
USER, PW = "alice", "alice123"


def login() -> requests.Session:
    s = requests.Session()
    # 1. Start SSO at the SP -> redirect to Keycloak
    r = s.get(f"{SP}/saml/login", allow_redirects=False)
    assert r.status_code == 302, f"/saml/login -> {r.status_code}"
    kc_url = r.headers["Location"]

    # 2. Keycloak login page
    r = s.get(kc_url)
    r.raise_for_status()
    for c in s.cookies:                 # Keycloak marks AUTH_SESSION_ID Secure; drop it for localhost http
        c.secure = False
    m = re.search(r'id="kc-form-login"[^>]+action="([^"]+)"', r.text) or re.search(r'action="([^"]+)"', r.text)
    action = html.unescape(m.group(1))

    # 3. Submit credentials -> HTML form that auto-POSTs the SAMLResponse to the SP's ACS
    r = s.post(action, data={"username": USER, "password": PW, "credentialId": ""})
    if "SAMLResponse" not in r.text:
        err = re.search(r'id="input-error[^"]*"[^>]*>\s*([^<]+)', r.text)
        print("ERROR: no SAMLResponse after login.", "Keycloak:", err.group(1).strip() if err else f"HTTP {r.status_code}")
        sys.exit(2)
    acs_url = html.unescape(re.search(r'<form[^>]+action="([^"]+)"', r.text).group(1))
    saml_response = re.search(r'name="SAMLResponse"\s+value="([^"]*)"', r.text).group(1)
    relay = re.search(r'name="RelayState"\s+value="([^"]*)"', r.text)
    form = {"SAMLResponse": html.unescape(saml_response)}
    if relay:
        form["RelayState"] = html.unescape(relay.group(1))

    # 4. Post the assertion to the SP's ACS -> SP verifies the signature and sets the session cookie
    r = s.post(acs_url, data=form, allow_redirects=False)
    assert r.status_code == 302, f"/saml/acs -> {r.status_code}: {r.text[:300]}"
    assert "saml_session" in s.cookies, "no saml_session cookie after ACS"
    return s


def probe(s, method, path, body=None, use_session=True):
    cookies = s.cookies if use_session else {}
    r = requests.request(method, SP + path, json=body, cookies=cookies, timeout=10)
    return r.status_code, r.text[:200]


def main():
    print("=== 1. Guest write (no session) -> /users/ ===")
    sc, _ = probe(requests.Session(), "POST", "/users/", body={"username": "x", "email": "x@example.com"}, use_session=False)
    print("   HTTP", sc, "(expect 401)")

    print("=== 2. Guest read -> /users/ ===")
    print("   HTTP", requests.get(SP + "/users/").status_code, "(expect 200)")

    print("=== 3. Driving SAML SSO as", USER, "===")
    s = login()
    print("   OK  saml_session set:", s.cookies.get("saml_session")[:16] + "...")

    print("=== 4. /me WITH session ===")
    sc, b = probe(s, "GET", "/me"); print("   HTTP", sc, "(expect 200)", "|", b)

    print("=== 5. Write WITH session -> /users/ ===")
    sc, b = probe(s, "POST", "/users/", body={"username": "saml_alice", "email": "saml.alice@example.com"})
    print("   HTTP", sc, "(expect 201)", "|", b)


if __name__ == "__main__":
    main()
