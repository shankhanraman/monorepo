"""Call a lab service over mTLS with a chosen identity. Runs in the `client` container (certs at /certs).

    docker compose run --rm client call.py --as admin GET https://orders-app:8443/whoami
    docker compose run --rm client call.py --as admin POST https://users-app:8443/users/ '{"username":"carol","email":"c@x.io"}'
    docker compose run --rm client call.py --as reporting GET https://orders-app:8443/orders/
    docker compose run --rm client call.py --no-cert GET https://orders-app:8443/whoami      (refused)
    docker compose run --rm client call.py --foreign GET https://orders-app:8443/whoami      (refused: wrong CA)
"""

import argparse
import json
import ssl
import sys

import httpx

CA = "/certs/ca.crt"  # we also verify the SERVER: it must present a cert from the lab CA for its hostname


def client(identity: str | None = None, foreign: bool = False) -> httpx.Client:
    """An HTTPS client that trusts only the lab CA and presents the chosen identity's certificate (if any)."""
    tls = ssl.create_default_context(cafile=CA)  # verify the server too: lab CA + hostname
    if foreign:
        tls.load_cert_chain("/certs/foreign/admin.crt", "/certs/foreign/admin.key")
    elif identity:
        tls.load_cert_chain(f"/certs/{identity}.crt", f"/certs/{identity}.key")
    return httpx.Client(verify=tls, timeout=10)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--as", dest="identity", help="lab identity: admin, reporting, orders, users")
    who.add_argument("--no-cert", action="store_true", help="present no client certificate")
    who.add_argument("--foreign", action="store_true", help="present an 'admin' cert from an untrusted CA")
    p.add_argument("method")
    p.add_argument("url")
    p.add_argument("body", nargs="?", help="JSON body")
    p.add_argument("-H", "--header", action="append", default=[], help="extra header 'Name: value'")
    a = p.parse_args()

    headers = dict(h.split(":", 1) for h in a.header)
    headers = {k.strip(): v.strip() for k, v in headers.items()}
    try:
        with client(a.identity, a.foreign) as c:
            r = c.request(a.method, a.url, json=json.loads(a.body) if a.body else None, headers=headers)
    except httpx.TransportError as e:
        print(f"connection refused by the server's TLS layer: {type(e).__name__}: {e}")
        return 1
    print(r.status_code, r.text)
    return 0 if r.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
