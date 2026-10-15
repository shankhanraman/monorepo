"""Who is calling? Answered by the Envoy sidecar, never by the app itself.

The sidecar terminates mTLS: it only lets a request through if the caller presented a certificate from the lab CA
(not revoked, not expired). It then sets `x-forwarded-client-cert` (XFCC) to the verified certificate's SPIFFE ID,
replacing anything the caller sent (forward_client_cert_details: SANITIZE_SET).

Trusting this header is only safe because the app listens on 127.0.0.1 inside the sidecar's network namespace:
nothing can reach the app without going through the sidecar.
"""

from fastapi import Depends, HTTPException, Request

TRUST_DOMAIN = "spiffe://lab.local/"


def caller_identity(request: Request) -> str:
    """The calling workload's name, e.g. "orders" for spiffe://lab.local/orders."""
    xfcc = request.headers.get("x-forwarded-client-cert")
    if not xfcc:
        raise HTTPException(401, "No verified client certificate (requests must come through the sidecar)")
    # XFCC = comma-separated elements (one per proxy hop) of key=value pairs separated by ";".
    # SANITIZE_SET leaves exactly one element: the one our own sidecar wrote.
    for pair in xfcc.split(",")[-1].split(";"):
        key, _, value = pair.partition("=")
        value = value.strip().strip('"')
        if key.strip() == "URI" and value.startswith(TRUST_DOMAIN):
            return value[len(TRUST_DOMAIN):]
    raise HTTPException(401, "Client certificate has no spiffe://lab.local/ identity")


def cert_hash(request: Request) -> str | None:
    """SHA-256 of the caller's certificate (changes on every re-issue, which is handy to see rotation)."""
    for pair in request.headers.get("x-forwarded-client-cert", "").split(",")[-1].split(";"):
        key, _, value = pair.partition("=")
        if key.strip() == "Hash":
            return value.strip()
    return None


def require_caller(*allowed: str):
    """Authorization by workload identity: a valid certificate isn't enough, the caller must be on the list."""

    def check(caller: str = Depends(caller_identity)) -> str:
        if caller not in allowed:
            raise HTTPException(403, f"'{caller}' is not allowed to call this endpoint")
        return caller

    return Depends(check)
