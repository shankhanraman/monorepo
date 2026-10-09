from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SessionRow(Base):
    """A signed-in browser. The browser holds a random token in an HttpOnly cookie; only its hash is stored here."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256 hex of the cookie value
    sub: Mapped[str] = mapped_column(String)  # Keycloak user id
    username: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Kept server-side only, to end the Keycloak session on logout (back-channel). Never sent to the browser.
    # ponytail: stored as plain text, encrypt at rest (e.g. Fernet/KMS) before production
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)  # UTC, naive
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC, naive
