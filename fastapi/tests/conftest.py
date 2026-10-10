import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import Base, get_db
from app.main import app

# Tests use a fresh in-memory SQLite database each, so they need no Postgres and no password.
# TestClient is used without `with`, so the startup hook (which connects to Postgres) doesn't run.


@pytest.fixture
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(engine)

    def override_get_db():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()
