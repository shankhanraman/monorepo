from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

from app.dependencies import Base, create_database_if_missing, engine
from app.models import items as _items  # noqa: F401  (registers the items table on Base)
from app.routers import items


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Runs once at startup: create the database and tables if they don't exist yet.
    # ponytail: create_all only adds missing tables; changing a column later needs a migration tool (Alembic)
    try:
        create_database_if_missing()
        Base.metadata.create_all(engine)
    except OperationalError as e:
        url = engine.url
        raise RuntimeError(
            f"Cannot connect to PostgreSQL at {url.host}:{url.port} as '{url.username}'. "
            f"Check DB_HOST / DB_PORT / DB_USER / DB_PASSWORD in .env. Original error: {e.orig}"
        ) from None
    yield


app = FastAPI(title="Items CRUD", lifespan=lifespan)
app.include_router(items.router)


@app.get("/health")
def health():
    return {"status": "ok"}
