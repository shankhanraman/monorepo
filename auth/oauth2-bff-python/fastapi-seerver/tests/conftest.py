import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

# Tests use a fresh in-memory SQLite database each, so they need no Docker/Postgres.
# Postgres itself is exercised by `alembic upgrade head` and the live checks in the README.


@pytest.fixture(autouse=True)
def test_db():
    # One shared in-memory connection, usable from FastAPI's worker threads.
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")  # SQLite ignores ON DELETE CASCADE without it

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(engine)

    def override_get_db():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestSession  # tests that need direct DB access (e.g. to create a session) take `test_db`
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()
