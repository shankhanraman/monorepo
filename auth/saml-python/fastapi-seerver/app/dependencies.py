from fastapi import Depends, HTTPException, Request

from app.saml import read_session

# After a successful SAML login we issue this HttpOnly cookie; it carries the SAML NameID.
SESSION_COOKIE = "saml_session"


def current_user(request: Request) -> dict:
    """The whole check for protected routes: a valid session cookie (set only after SAML succeeded)."""
    sub = read_session(request.cookies.get(SESSION_COOKIE))
    if not sub:
        raise HTTPException(401, "Not signed in")
    return {"sub": sub}


# Put on endpoints that change data: `@router.post(..., dependencies=require_login)`. Reads stay public.
require_login = [Depends(current_user)]
