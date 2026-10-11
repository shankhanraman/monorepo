import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import close_db, init_db, pool
from app.routers import ask, banks, collections, notes, sources
from app.services import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    jobs.recover()
    yield
    close_db()


app = FastAPI(title="Media Insight Engine API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/health", tags=["health"])
def health():
    with pool().connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


for r in (collections, sources, ask, banks, notes):
    app.include_router(r.router)
