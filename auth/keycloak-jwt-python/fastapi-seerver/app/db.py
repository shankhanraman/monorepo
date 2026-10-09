from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.dependencies import settings

# Connects lazily: the app starts (and tests run) without a database. pool_pre_ping drops dead connections,
# e.g. after a Postgres restart or an idle timeout on AWS RDS.
engine = create_engine(settings["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    """Parent of all tables. Schema changes go through Alembic migrations (migrations/), never create_all."""


def get_db() -> Iterator[Session]:
    """One session per request; closing it rolls back anything not committed."""
    with SessionLocal() as session:
        yield session
