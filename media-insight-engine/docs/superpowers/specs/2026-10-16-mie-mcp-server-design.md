# Media Insight Engine — MCP Server (design)

**Date:** 2026-10-16
**Status:** Approved, ready for planning

## Goal

Expose the Media Insight Engine's tools and agents over the Model Context Protocol so an
MCP client (Claude Desktop / Claude Code, etc.) can **operate the whole engine** — query the
knowledge base *and* manage it (sync, question banks, notes, insights).

## Decisions

- **Scope:** full control — query + management.
- **Integration:** mount the MCP server *inside* the existing FastAPI app (one process), served
  alongside `/docs` and `/health`.
- **SDK:** the official MCP Python SDK (`mcp`, `FastMCP`), hand-authored tools.
- **Transport:** streamable-HTTP, mounted at `/mcp`. Localhost-only, no auth (matches the
  existing localhost CORS posture).

## Architecture

New module `server/app/mcp_server.py` builds a `FastMCP` instance and its ASGI app, which
`main.py` mounts at `/mcp`.

Three load-bearing details, confirmed against the code:

1. **Tools call the router functions in-process, not the raw service functions.** Routers hold
   behavior the services don't:
   - `ask.py` calls `answers.ask(...)` **then** `answers.save(...)` — service alone never persists.
   - `banks.create_bank` does question dedup, 3–2000 length validation, and `upsert_collection`
     when the collection row is missing.
   - `collections.get_insights` computes the `stale` flag with extra queries.
   Each tool builds the Pydantic request model, calls the router function, and catches
   `fastapi.HTTPException`, re-raising as an MCP `ToolError` carrying `{status_code, detail}`.
   This reuses all validation + error translation.

2. **Blocking work is offloaded off the event loop.** `answers.ask` and insights call Claude
   synchronously; in-process they share the API's event loop. Verify how the pinned `mcp` SDK
   runs handlers: if FastMCP offloads sync (`def`) tool handlers to a worker thread (like FastAPI
   sync routes), keep tools sync; otherwise make them `async def` and wrap the blocking call in
   `anyio.to_thread.run_sync(...)`. A Q&A call must never stall `/health` or `/docs`.

3. **Lifespan is composed.** `streamable_http_app()`'s session manager runs a task group in its
   own lifespan. `main.py`'s existing `lifespan` must also enter the MCP session manager's
   context, or the first request crashes with "task group not initialized."

## Tool surface (~17 tools)

**Agents (the intelligence)**
- `ask_collection(collection_id, question, history?, filters?)` → cited answer; persists it.
- `get_collection_insights(collection_id)` → synthesis (themes / consensus / coverage / timeline + `stale`).
- `refresh_collection_insights(collection_id)` → starts background synthesis, returns immediately.
- `run_question_bank(bank_id, filters?)` → starts a run, returns `run_id`.
- `get_bank_run(run_id)` → run status + per-question answers (poll target).

**Browse / query**
- `list_collections()`
- `list_sources(collection_id, include_archived?)`
- `get_source(source_id)` → segments / chapters / quotes with deep links.
- `get_sync_log(collection_id)` → latest sync log.

**Management (write)**
- `sync_collection(collection)` → returns sync log immediately; poll `list_sources` for ingest status.
- `create_question_bank(collection_id, name, questions)`
- `list_question_banks(collection_id)`
- `delete_question_bank(bank_id)`
- `get_bank_report(run_id)` → **markdown** report. (PDF export omitted — binary is awkward/heavy over MCP.)
- `list_notes(collection?)`
- `create_note(...)`
- `delete_note(note_id)`

## Long-running jobs: start → poll

`sync_collection`, `refresh_collection_insights`, and `run_question_bank` return fast; each has a
matching poll tool (`list_sources`, `get_collection_insights`, `get_bank_run`). Tool descriptions
state this explicitly so the agent polls rather than assuming completion.

## Error handling

Router `HTTPException` → MCP `ToolError` with the status code and detail string. Config/validation
errors (422), not-found (404), and conflicts (409, e.g. `SyncBusy`, `RunBusy`) surface as readable
tool errors.

## Testing

- Unit: `HTTPException` → `ToolError` translation helper.
- Smoke: list tools via an in-memory MCP client session and assert the expected tool names/schemas.
- Keep consistent with the existing `server/tests` layout and the pure/contract split noted in
  project memory (tests runnable without Docker where possible).

## Dependencies

Add `mcp` (official SDK) to `server/requirements.txt`, pinned. Confirm it does not conflict with
the pinned `anthropic`, `fastapi`, `pydantic`, `starlette` versions.

## Out of scope

- Authentication / remote exposure (localhost only for now).
- PDF export over MCP.
- A separate standalone MCP process (we mount in-process per the decision above).
