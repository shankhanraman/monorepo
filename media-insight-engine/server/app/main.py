import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import close_db, init_db, pool
from app.mcp_server import mcp, mcp_app
from app.routers import ask, banks, collections, notes, sources
from app.services import audio, jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logging.getLogger("audio").info("speech-to-text backend: %s", audio.backend())  # bad WHISPER_DEVICE fails here
    jobs.recover()
    # The MCP server is mounted as a sub-app; FastAPI doesn't run a mount's lifespan, so enter the
    # streamable-HTTP session manager here (it exists once mcp_server built mcp_app at import).
    async with mcp.session_manager.run():
        yield
    close_db()


app = FastAPI(title="Media Insight Engine API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/health", tags=["health"])
def health():
    with pool().connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "whisper": audio.backend()}


for r in (collections, sources, ask, banks, notes):
    app.include_router(r.router)

# MCP server over streamable-HTTP at /mcp (mounts are excluded from the OpenAPI contract).
app.mount("/mcp", mcp_app)
