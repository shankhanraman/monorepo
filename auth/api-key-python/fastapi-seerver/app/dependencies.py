from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.apikeys import ApiKeyRow, hash_key

# Writes send the key in this header. auto_error=False so a missing key is our 401, not FastAPI's 403.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def current_key(
    presented: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> ApiKeyRow:
    """The whole check: hash the presented key, find an active row with that hash, else 401."""
    if not presented:
        raise HTTPException(401, "Missing API key", headers={"WWW-Authenticate": "X-API-Key"})
    row = db.scalar(
        select(ApiKeyRow).where(ApiKeyRow.key_hash == hash_key(presented), ApiKeyRow.active.is_(True))
    )
    if row is None:
        raise HTTPException(401, "Invalid or revoked API key")
    return row


# Put on endpoints that change data: `@router.post(..., dependencies=require_login)`. Reads stay public.
require_login = [Depends(current_key)]
