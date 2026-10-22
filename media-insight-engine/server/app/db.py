"""psycopg 3 connection pool with pgvector; the schema is applied before the pool opens."""
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import secrets
from app.config import settings

_pool: ConnectionPool | None = None


def init_db() -> None:
    global _pool
    # Mutual-TLS cert auth: fetch the client cert from Vault and connect with sslmode=verify-full.
    # Password auth (default) adds nothing here. Fails fast with a clear error if Vault/certs are bad.
    ssl = secrets.ensure_db_certs() if settings.db_auth == "cert" else {}
    schema = (Path(__file__).parent.parent / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(settings.database_url, autocommit=True, **ssl) as conn:
        conn.execute("SELECT pg_advisory_lock(424242)")  # two processes starting at once
        conn.execute(schema)
        conn.execute("SELECT pg_advisory_unlock(424242)")
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=True,
                               kwargs={"autocommit": True, "row_factory": dict_row, **ssl},
                               configure=register_vector)


def pool() -> ConnectionPool:
    if _pool is None:
        init_db()
    return _pool


def close_db() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
