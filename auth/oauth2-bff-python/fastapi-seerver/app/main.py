from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import current_user
from app.routers import auth, profiles, users

app = FastAPI(title=settings["APP_NAME"])


@app.exception_handler(IntegrityError)
def conflict(_: Request, exc: IntegrityError) -> JSONResponse:
    # Unique username/email (or, in a race, a profile whose user was just deleted). The session is rolled back by get_db.
    return JSONResponse(status_code=409, content={"detail": "Already exists (username and email must be unique)"})


# No CORS middleware: the browser reaches /api and /auth through the site's own origin (Vite proxy in dev,
# ingress path routing in production), so every request is same-origin and the session cookie is first-party.

# Reads are public; each write endpoint declares `dependencies=require_login` (session + X-CSRF header) itself.
app.include_router(users.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(auth.router)  # /auth/login, /auth/register, /auth/callback, /auth/logout


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    """Who is signed in (401 for guests). The SPA calls this once on load."""
    return {"username": user["preferred_username"], "email": user["email"]}
