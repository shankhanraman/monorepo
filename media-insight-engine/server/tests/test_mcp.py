"""The MCP server must expose every engine tool and translate router errors into ToolErrors.

Pure tests: they import the module and inspect the registered tools; no DB or network needed.
"""
import asyncio
import datetime
import json

import pytest
from fastapi import HTTPException
from mcp.server.mcpserver.exceptions import ToolError

from app import mcp_server

EXPECTED_TOOLS = {
    # agents
    "ask_collection", "get_collection_insights", "refresh_collection_insights",
    "run_question_bank", "get_bank_run",
    # browse / query
    "list_collections", "list_sources", "get_source", "get_sync_log",
    # management
    "sync_collection", "list_question_banks", "create_question_bank", "delete_question_bank",
    "get_bank_report", "list_notes", "create_note", "delete_note",
}


def _tools():
    return {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_every_tool_is_registered():
    assert set(_tools()) == EXPECTED_TOOLS


def test_tools_have_descriptions():
    for name, tool in _tools().items():
        assert tool.description, f"{name} has no description"


def test_ask_tool_input_schema():
    schema = _tools()["ask_collection"].input_schema
    props = schema["properties"]
    assert {"collection_id", "question"} <= set(props)
    assert set(schema.get("required", [])) == {"collection_id", "question"}  # history/filters optional


def test_guard_translates_http_exception():
    def boom():
        raise HTTPException(409, "Sync already running")

    with pytest.raises(ToolError) as e:
        mcp_server._guard(boom)
    assert "409" in str(e.value) and "Sync already running" in str(e.value)


def test_guard_passes_through_return_value():
    assert mcp_server._guard(lambda x: x + 1, 41) == 42


def _call(name, args):
    return asyncio.run(mcp_server.mcp.call_tool(name, args))


def test_list_tool_round_trips_through_dump(monkeypatch):
    # _dump list branch: router returns dicts + datetime; output must be JSON-safe (ISO dates).
    canned = [{
        "id": "yale", "name": "Yale", "lens_name": "admissions", "lens_tags": ["essays"],
        "focus_note": None, "segment_seconds": 60,
        "source_counts": {"total": 3, "ready": 2, "in_progress": 0, "failed": 1, "archived": 0},
        "last_synced_at": datetime.datetime(2026, 10, 16, 12, 0, 0),
    }]
    monkeypatch.setattr(mcp_server.collections_router, "list_collections", lambda: canned)
    res = _call("list_collections", {})
    assert not res.is_error
    rows = res.structured_content["result"]
    assert rows[0]["id"] == "yale"
    assert rows[0]["last_synced_at"] == "2026-10-16T12:00:00"  # datetime -> ISO string


def test_scalar_tool_round_trips_through_dump(monkeypatch):
    # _dump single-object branch via SyncLog. A bare dict return is delivered as JSON text content.
    canned = {
        "id": 7, "collection_id": "yale",
        "created_at": datetime.datetime(2026, 10, 16, 9, 30, 0),
        "summary": {"queued": 1, "skipped": 0, "failed": 0, "archived": 0},
        "entries": [{"url": "https://x", "label": None, "action": "queued",
                     "reason": "new", "source_id": 5}],
    }
    monkeypatch.setattr(mcp_server.collections_router, "sync", lambda collection: canned)
    res = _call("sync_collection", {"collection": "yale"})
    assert not res.is_error
    out = json.loads(res.content[0].text)
    assert out["id"] == 7 and out["created_at"] == "2026-10-16T09:30:00"  # datetime -> ISO string
    assert out["entries"][0]["action"] == "queued"


def test_http_exception_surfaces_as_tool_error(monkeypatch):
    # A router HTTPException becomes a ToolError carrying the status + detail, propagated by call_tool.
    def boom(collection):
        raise HTTPException(409, "Sync already running for 'yale'")

    monkeypatch.setattr(mcp_server.collections_router, "sync", boom)
    with pytest.raises(ToolError) as e:
        _call("sync_collection", {"collection": "yale"})
    assert "409" in str(e.value) and "already running" in str(e.value)


def test_mcp_mount_absent_from_openapi_contract():
    # Mounts must not leak into the OpenAPI schema (the frontend contract is exact).
    from app.main import app
    assert not any(p.startswith("/mcp") for p in app.openapi()["paths"])
