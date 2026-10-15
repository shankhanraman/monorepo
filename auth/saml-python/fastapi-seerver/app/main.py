from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import current_user
from app.routers import profiles, saml, users

app = FastAPI(title=settings["APP_NAME"])


@app.exception_handler(IntegrityError)
def conflict(_: Request, exc: IntegrityError) -> JSONResponse:
    # Unique username/email (or, in a race, a profile whose user was just deleted). The session is rolled back by get_db.
    return JSONResponse(status_code=409, content={"detail": "Already exists (username and email must be unique)"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings["CORS_ORIGIN"]],
    allow_methods=["*"],
    allow_headers=["Content-Type"],
)

# Reads are public; each write endpoint declares `dependencies=require_login` itself.
app.include_router(users.router)
app.include_router(profiles.router)
app.include_router(saml.router)  # /saml/login, /saml/acs, /saml/metadata


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: dict = Depends(current_user)):
    """Who is signed in (the SAML NameID). 401 for guests."""
    return {"sub": user["sub"]}
