# MCP server

The engine exposes its tools and agents over the [Model Context Protocol](https://modelcontextprotocol.io)
so an MCP client (Claude Desktop, Claude Code, …) can operate it. The server is **mounted inside the
API process** (`app/mcp_server.py`, built on the official `mcp` SDK) and served over streamable-HTTP.

| | |
|---|---|
| Endpoint | `http://localhost:8003/mcp` (transport: streamable-HTTP) |
| Auth | none — localhost only, same posture as the API's CORS |

Each tool calls the matching FastAPI router function in-process, so it inherits the HTTP API's
validation, persistence and error handling; router `HTTPException`s surface as MCP tool errors.

## Connect

**Claude Code** (CLI):
```bash
claude mcp add --transport http media-insight-engine http://localhost:8003/mcp
```

**Claude Desktop / other clients** — add to the client's MCP config:
```json
{
  "mcpServers": {
    "media-insight-engine": {
      "type": "http",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

Notes:
- The API must be running (`docker compose up`). The MCP endpoint comes up with it.
- The endpoint canonicalizes to `/mcp/`; a request to `/mcp` returns a 307 to it, which MCP clients
  follow automatically.
- Requests must carry a `Host` of `localhost:<port>` or `127.0.0.1:<port>` (built-in DNS-rebinding
  protection for localhost). Reaching the server under another hostname returns `421`.

## Tools

**Agents** — `ask_collection`, `get_collection_insights`, `refresh_collection_insights`,
`run_question_bank`, `get_bank_run`.

**Browse** — `list_collections`, `list_sources`, `get_source`, `get_sync_log`.

**Manage** — `sync_collection`, `create_question_bank`, `list_question_banks`,
`delete_question_bank`, `get_bank_report`, `list_notes`, `create_note`, `delete_note`.

Long-running work is start-then-poll: `sync_collection`, `refresh_collection_insights` and
`run_question_bank` return immediately; poll `list_sources`, `get_collection_insights` and
`get_bank_run` respectively until they settle.
