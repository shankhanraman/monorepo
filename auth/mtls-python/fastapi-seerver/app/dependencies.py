import re

from fastapi import Depends, Header, HTTPException

# nginx terminates TLS, verifies the client certificate against our CA, and forwards the result
# in these two headers. FastAPI trusts them because it is reachable ONLY through nginx (the server
# container is not published to the host); a direct caller can't reach it to forge them.
#   X-SSL-Client-Verify:  SUCCESS | FAILED:... | NONE
#   X-SSL-Client-DN:      the client cert subject, e.g. "CN=alice"


def _cn(dn: str | None) -> str | None:
    """Pull the CN out of a subject DN like 'CN=alice,O=lab'."""
    m = re.search(r"CN=([^,/]+)", dn or "")
    return m.group(1) if m else None


def current_cert(
    x_ssl_client_verify: str | None = Header(default=None),
    x_ssl_client_dn: str | None = Header(default=None),
) -> dict:
    """The whole check: nginx must have verified a client cert (SUCCESS), else 401."""
    if x_ssl_client_verify != "SUCCESS":
        raise HTTPException(401, "Valid client certificate required",
                            headers={"WWW-Authenticate": "Certificate"})
    return {"cn": _cn(x_ssl_client_dn)}


# Put on endpoints that change data: `@router.post(..., dependencies=require_login)`. Reads stay public.
require_login = [Depends(current_cert)]
