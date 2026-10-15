import hashlib

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def hash_key(key: str) -> str:
    """We store only the SHA-256 of a key, never the key itself."""
    return hashlib.sha256(key.encode()).hexdigest()


# --- table ---

class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String)                       # who/what the key is for
    prefix: Mapped[str] = mapped_column(String)                     # first chars, to identify a key without its secret
    key_hash: Mapped[str] = mapped_column(String, unique=True)      # SHA-256 of the key
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


# --- API schema (what /me returns: never the hash) ---

class ApiKeyInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    prefix: str
