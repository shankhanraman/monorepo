"""MCP server for the Media Insight Engine, mounted in-process at /mcp.

Every tool calls the matching FastAPI *router* function (not the raw service), so it inherits the
router's behavior — persisting answers, validating/ deduping question banks, computing the insights
`stale` flag — and its error translation. Router `HTTPException`s become MCP `ToolError`s. Results
are coerced through the same Pydantic response models the HTTP API uses, so output is JSON-safe
(dates as ISO strings).

Tool handlers are plain sync `def`: mcp 2.x runs sync tools on a worker thread
(`anyio.to_thread.run_sync`), so the blocking DB/Claude calls never stall the shared event loop.
"""
from typing import Any

from fastapi import HTTPException
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from app.models.api import (
    AskFilters,
    AskRequest,
    AskResponse,
    Collection,
    CollectionAnalysis,
    HistoryTurn,
    Note,
    NoteCreate,
    QuestionBank,
    QuestionBankCreate,
    RunRequest,
    SourceDetail,
    SourceSummary,
    SyncLog,
    BankRun,
)
from app.routers import ask as ask_router
from app.routers import banks as banks_router
from app.routers import collections as collections_router
from app.routers import notes as notes_router
from app.routers import sources as sources_router
from app.services import banks as banks_service

INSTRUCTIONS = """Operate the Admissions Media Insight Engine: a cited knowledge base built from
admissions videos, podcasts, web pages and PDFs, organized into per-college collections.

Use `list_collections` to discover collection ids. `ask_collection` answers a question only from a
collection's sources, with citations. `get_collection_insights` returns the home-page synthesis
(themes, contradictions, trends, gaps, coverage, timeline).

Long-running work is start-then-poll: `sync_collection`, `refresh_collection_insights` and
`run_question_bank` return immediately; poll `list_sources`, `get_collection_insights` and
`get_bank_run` respectively until they settle."""

mcp = MCPServer("media-insight-engine", instructions=INSTRUCTIONS)


def _guard(fn, *args, **kwargs):
    """Call a router function, turning its HTTPException into an MCP ToolError."""
    try:
        return fn(*args, **kwargs)
    except HTTPException as e:
        raise ToolError(f"{e.status_code}: {e.detail}") from e


def _dump(model: type[BaseModel], value: Any) -> Any:
    """Coerce a router return (dict / row / list thereof) through its response model to JSON-safe data."""
    if isinstance(value, list):
        return [model.model_validate(v).model_dump(mode="json") for v in value]
    return model.model_validate(value).model_dump(mode="json")

# ---------------------------------------------------------------- agents (the intelligence)

@mcp.tool(description="Answer a question using ONLY a collection's sources, with citations and "
                      "coverage. Persists the answer. `filters` can scope to source_ids, tags or a "
                      "date range; `history` carries prior turns for follow-ups.")
def ask_collection(collection_id: str, question: str,
                   history: list[HistoryTurn] | None = None,
                   filters: AskFilters | None = None) -> dict:
    body = AskRequest(question=question, history=history or [], filters=filters or AskFilters())
    return _dump(AskResponse, _guard(ask_router.ask, body=body, collection_id=collection_id))


@mcp.tool(description="Collection-wide synthesis for the home page: themes, contradictions, trends, "
                      "gaps, consensus, coverage and timeline. `status` is 'empty' until the first "
                      "run finishes and 'running' while regenerating; `stale` means sources changed "
                      "since it ran. Poll this after refresh_collection_insights.")
def get_collection_insights(collection_id: str) -> dict:
    return _dump(CollectionAnalysis, _guard(collections_router.get_insights, collection_id))


@mcp.tool(description="Re-run the analytical agent for a collection (for a failed or stale result). "
                      "Returns immediately; the synthesis runs in the background — poll "
                      "get_collection_insights until `status` leaves 'running'.")
def refresh_collection_insights(collection_id: str) -> dict:
    return _dump(CollectionAnalysis, _guard(collections_router.refresh_insights, collection_id))


@mcp.tool(description="Start a question-bank run: batch-ask every question in the bank. Returns a "
                      "BankRun with status 'running'; poll get_bank_run(run_id) until it is 'done' "
                      "or 'failed'. `filters` optionally scopes the sources used.")
def run_question_bank(bank_id: int, filters: AskFilters | None = None) -> dict:
    body = RunRequest(filters=filters or AskFilters())
    return _dump(BankRun, _guard(banks_router.run_bank, bank_id, body))


@mcp.tool(description="Get a question-bank run's status and per-question answers. Poll target for "
                      "run_question_bank.")
def get_bank_run(run_id: int) -> dict:
    return _dump(BankRun, _guard(banks_router.get_run, run_id))


# ---------------------------------------------------------------- browse / query

@mcp.tool(description="List all collections with their lens and source counts.")
def list_collections() -> list[dict]:
    return _dump(Collection, _guard(collections_router.list_collections))


@mcp.tool(description="List a collection's sources (videos, podcasts, web pages, PDFs) with status. "
                      "Set include_archived to also return archived sources. Poll this after "
                      "sync_collection to watch ingest progress (status ready/failed).")
def list_sources(collection_id: str, include_archived: bool = False) -> list[dict]:
    return _dump(SourceSummary, _guard(collections_router.list_sources, collection_id, include_archived))


@mcp.tool(description="Get one source in full: overview, chapters, segments and key quotes, each "
                      "with a deep link to the exact minute or paragraph.")
def get_source(source_id: int) -> dict:
    return _dump(SourceDetail, _guard(sources_router.get_source, source_id))


@mcp.tool(description="Get the latest sync log for a collection (what was queued/skipped/failed/archived).")
def get_sync_log(collection_id: str) -> dict:
    return _dump(SyncLog, _guard(collections_router.latest_sync_log, collection_id))

# ---------------------------------------------------------------- management (write)

@mcp.tool(description="Sync a collection from its config file: queue new/changed sources for ingest "
                      "and archive removed ones. Returns the sync log immediately (ingest runs in "
                      "the background) — poll list_sources until sources reach 'ready' or 'failed'.")
def sync_collection(collection: str) -> dict:
    return _dump(SyncLog, _guard(collections_router.sync, collection=collection))

@mcp.tool(description="List a collection's saved question banks.")
def list_question_banks(collection_id: str) -> list[dict]:
    return _dump(QuestionBank, _guard(banks_router.list_banks, collection_id))

@mcp.tool(description="Create a saved question bank (a named list of questions, each 3-2000 chars). "
                      "Duplicates are removed.")
def create_question_bank(collection_id: str, name: str, questions: list[str]) -> dict:
    body = QuestionBankCreate(name=name, questions=questions)
    return _dump(QuestionBank, _guard(banks_router.create_bank, collection_id, body))

@mcp.tool(description="Delete a question bank by id.")
def delete_question_bank(bank_id: int) -> dict:
    _guard(banks_router.delete_bank, bank_id)
    return {"deleted": True, "bank_id": bank_id}


@mcp.tool(description="Get a finished bank run's report as Markdown. Errors if the run is still running.")
def get_bank_report(run_id: int) -> str:
    run = banks_service.get_run(run_id)
    if not run:
        raise ToolError("404: Not found")
    if run["status"] == "running":
        raise ToolError(f"409: Run {run_id} is still running")
    return banks_service.report_markdown(run)

@mcp.tool(description="List saved notes (pinned answers), optionally filtered to one collection.")
def list_notes(collection: str | None = None) -> list[dict]:
    return _dump(Note, _guard(notes_router.list_notes, collection))

@mcp.tool(description="Save a note: a pinned question/answer with its coverage, citations and an "
                      "optional comment.")
def create_note(body: NoteCreate) -> dict:
    return _dump(Note, _guard(notes_router.create_note, body))

@mcp.tool(description="Delete a note by id.")
def delete_note(note_id: int) -> dict:
    _guard(notes_router.delete_note, note_id)
    return {"deleted": True, "note_id": note_id}

# ASGI app for mounting at /mcp. streamable_http_path="/" so the mount point IS the endpoint.
mcp_app = mcp.streamable_http_app(streamable_http_path="/") 