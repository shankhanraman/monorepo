import os
from collections.abc import Iterator

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()  # reads .env; real environment variables win

# Built from separate settings, so a password with @ : / # etc. needs no URL-escaping.
DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD") or None,
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME", "crud_app"),
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """One database session per request."""
    with SessionLocal() as session:
        yield session


def create_database_if_missing() -> None:
    """Connect to the built-in 'postgres' database and create DB_NAME if it doesn't exist yet."""
    name = engine.url.database
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}):
                conn.execute(text(f"CREATE DATABASE {engine.dialect.identifier_preparer.quote(name)}"))
    finally:
        admin.dispose()
