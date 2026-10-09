import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.sessions import SessionRow


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, same on Postgres and SQLite


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, claims: dict, refresh_token: str | None, ttl_hours: int) -> str:
    """Store a new session from verified ID-token claims. Returns the raw token for the cookie (not stored)."""
    db.execute(delete(SessionRow).where(SessionRow.expires_at <= _now()))  # purge expired ones while we're here
    token = secrets.token_urlsafe(32)
    now = _now()
    db.add(SessionRow(
        id=_hash(token),
        sub=claims["sub"],
        username=claims.get("preferred_username") or claims["sub"],
        email=claims.get("email"),
        refresh_token=refresh_token,
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    ))
    db.commit()
    return token


def get_session(db: Session, token: str) -> SessionRow | None:
    """The live session for a cookie value, or None if unknown or expired."""
    row = db.get(SessionRow, _hash(token))
    return row if row is not None and row.expires_at > _now() else None


def delete_session(db: Session, token: str) -> SessionRow | None:
    """Remove a session (logout). Returns the removed row, so the caller can end the Keycloak session too."""
    row = db.get(SessionRow, _hash(token))
    if row is not None:
        db.delete(row)
        db.commit()
    return row
