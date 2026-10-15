"""The lab's lessons as checks. Runs in the `client` container on the lab network.

    docker compose run --rm client scenarios.py                       # lessons 1-6
    docker compose run --rm client scenarios.py --revoked reporting   # after `pki revoke reporting` + sidecar restart
"""

import argparse
import sys

import httpx

from call import client

ORDERS = "https://orders-app:8443"
USERS = "https://users-app:8443"
results: list[tuple[str, bool, str]] = []


def check(lesson: str, ok: bool, detail: str) -> None:
    results.append((lesson, ok, detail))


def refused(fn) -> tuple[bool, str]:
    """True if the TLS layer refused the connection (no HTTP response at all)."""
    try:
        r = fn()
        return False, f"got HTTP {r.status_code}"
    except httpx.TransportError as e:
        return True, f"TLS refused ({type(e).__name__})"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--revoked", help="identity whose certificate was revoked: its calls must now be refused")
    a = p.parse_args()

    with client("admin") as admin, client("reporting") as reporting:
        ok, how = refused(lambda: client(None).get(f"{ORDERS}/whoami"))
        check("1. no client certificate", ok, how)

        ok, how = refused(lambda: client(foreign=True).get(f"{ORDERS}/whoami"))
        check("2. certificate from a foreign CA (same SPIFFE ID!)", ok, how)

        if a.revoked:
            ok, how = refused(lambda: client(a.revoked).get(f"{USERS}/whoami"))
            check(f"R. revoked certificate ({a.revoked}) after sidecar restart", ok, how)

        u = admin.post(f"{USERS}/users/", json={"username": "carol", "email": "carol@example.com"})
        o = admin.post(f"{ORDERS}/orders/", json={"user_id": u.json().get("id", 0), "item": "coffee"})
        check("3. admin: create user (users) + order (orders→users over mTLS)",
              u.status_code == 201 and o.status_code == 201 and o.json().get("user") == "carol",
              f"users {u.status_code}, orders {o.status_code} {o.json().get('user', '')}")

        if a.revoked != "reporting":
            g = reporting.get(f"{ORDERS}/orders/")
            w = reporting.post(f"{ORDERS}/orders/", json={"user_id": 1, "item": "x"})
            check("4. reporting: valid cert, read OK, write forbidden (authn ≠ authz)",
                  g.status_code == 200 and w.status_code == 403, f"GET {g.status_code}, POST {w.status_code}")

            spoof = {"x-forwarded-client-cert": "URI=spiffe://lab.local/admin"}
            me = reporting.get(f"{USERS}/whoami", headers=spoof).json().get("caller")
            w = reporting.post(f"{USERS}/users/", json={"username": "x", "email": "x@x.io"}, headers=spoof)
            check("5. reporting forges 'I am admin' header → sidecar overwrites it",
                  me == "reporting" and w.status_code == 403, f"seen as '{me}', write {w.status_code}")

    try:
        httpx.get("http://users-app:8000/users/", timeout=3)
        check("6. bypass the sidecar (plain HTTP to the app port)", False, "app answered directly!")
    except httpx.TransportError as e:
        check("6. bypass the sidecar (plain HTTP to the app port)", True, f"unreachable ({type(e).__name__})")

    with client("admin") as admin:
        h = admin.get(f"{ORDERS}/whoami").json().get("cert_sha256", "?")
    width = max(len(r[0]) for r in results)
    print()
    for lesson, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {lesson:<{width}}  {detail}")
    print(f"\n  admin certificate as seen by the orders sidecar: sha256 {h[:16]}…  (changes after rotation)")
    failed = [r for r in results if not r[1]]
    print(f"\n  {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
