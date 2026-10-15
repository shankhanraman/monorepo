from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import current_cert
from app.routers import profiles, users

app = FastAPI(title=settings["APP_NAME"])


@app.exception_handler(IntegrityError)
def conflict(_: Request, exc: IntegrityError) -> JSONResponse:
    # Unique username/email (or, in a race, a profile whose user was just deleted). The session is rolled back by get_db.
    return JSONResponse(status_code=409, content={"detail": "Already exists (username and email must be unique)"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings["CORS_ORIGIN"]],
    allow_methods=["*"],
    allow_headers=["Content-Type"],  # the client cert rides the TLS handshake, not a browser header
)

# Reads are public; each write endpoint declares `dependencies=require_login` itself.
app.include_router(users.router)
app.include_router(profiles.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(cert: dict = Depends(current_cert)):
    """Which client certificate nginx verified (its CN)."""
    return {"cn": cert["cn"]}
