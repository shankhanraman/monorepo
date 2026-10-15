from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import current_key
from app.models.apikeys import ApiKeyInfo, ApiKeyRow
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
    allow_headers=["X-API-Key", "Content-Type"],  # the browser must be allowed to send the key header
)

# Reads are public; each write endpoint declares `dependencies=require_login` itself.
app.include_router(users.router)
app.include_router(profiles.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me", response_model=ApiKeyInfo)
def me(key: ApiKeyRow = Depends(current_key)):
    """Which key FastAPI accepted — name and prefix only, never the secret."""
    return key
