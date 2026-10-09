from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings  # noqa: F401  (re-exported for convenience)
from app.db import get_db
from app.services import sessions

SESSION_COOKIE = "bff_session"


def current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    """The signed-in user, from the HttpOnly session cookie. The browser never holds a token."""
    token = request.cookies.get(SESSION_COOKIE)
    row = sessions.get_session(db, token) if token else None
    if row is None:
        raise HTTPException(401, "Not signed in")
    return {"sub": row.sub, "preferred_username": row.username, "email": row.email}


def csrf_header(request: Request) -> None:
    """Cookies are sent automatically, so a write must also prove it comes from our own JavaScript.
    A cross-site form can't set custom headers, and cross-origin fetch() would need CORS (which is off)."""
    if request.headers.get("X-CSRF") != "1":
        raise HTTPException(403, "Missing X-CSRF header")


# Put on endpoints that change data: `@router.post(..., dependencies=require_login)`. Reads stay public.
# Order matters: no session → 401 first, then a missing CSRF header → 403.
require_login = [Depends(current_user), Depends(csrf_header)]
