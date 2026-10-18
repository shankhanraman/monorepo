# mie-copilot-marketplace

An **Agent Plugins 1.0** marketplace that publishes the **Media Insight Engine analyst**
agent (`mie-analyst`) plus the engine's **MCP server** to **GitHub Copilot in VS Code**.

The agent appears in the Copilot agent picker and is wired to the engine's MCP tools, so you
can ask it to browse collections, get cited answers, compute insights, run question banks and
manage notes — and it can read the MIE source in your workspace to explain how the engine works.

## Prerequisites

- The Media Insight Engine must be **running locally** — the MCP server points at
  `http://localhost:8003/mcp/`. Start it with `docker compose up -d` in `media-insight-engine/`.
- VS Code **1.102+** with GitHub Copilot + Copilot Chat signed in.
- AI tools (`ask_collection`, insights, question-bank runs) need the engine's
  `ANTHROPIC_API_KEY` to have credit; browse/manage tools work regardless.

## Install (consumers)

1. **Enable agent plugins**: set `chat.plugins.enabled` to `true` in VS Code settings.
2. **Add this marketplace** to `chat.plugins.marketplaces`. Because it lives inside the
   monorepo, the simplest path locally is a `file:///` URL to this folder:
   ```json
   {
     "chat.plugins.enabled": true,
     "chat.plugins.marketplaces": [
       "file:///C:/Users/workf/OneDrive/Desktop/monorepo/mie-copilot-plugin"
     ]
   }
   ```
   (If you later push this as its own GitHub repo, you can instead use `"<owner>/<repo>"`
   or an HTTPS `.git` URL.)
3. Open the **Extensions view** and search `@agentPlugins`, then install **media-insight**.
4. Pick **mie-analyst** from the Copilot **agent picker**. Its MCP server is trusted
   automatically — no startup trust prompt.

> There is no one-click `vscode:` deep link for adding a marketplace yet; the steps above
> are the supported flow.

## Authoring (maintainers)

```bash
npm run new:plugin -- <plugin-name> "description"
npm run new:agent  -- <plugin-name> <agent-name> --copilot-only "description"
npm run new:mcp    -- <plugin-name> <server-name> --http http://localhost:8003/mcp/
npm run validate
```

- Copilot agents live in `plugins/<name>/com.github.copilot/agents/*.agent.md` and use
  **namespaced** tool names (e.g. `search/codebase`, `media-insight-engine/*`) — see
  https://code.visualstudio.com/docs/agents/reference/tools-reference.
- MCP servers live in `plugins/<name>/mcp.json`.
- Run `npm run validate` before every commit.

## Layout

```
.claude-plugin/marketplace.json              # lists every plugin
plugins/media-insight/
  plugin.json                                # Agent Plugins 1.0 manifest
  mcp.json                                   # media-insight-engine HTTP MCP server
  com.github.copilot/agents/mie-analyst.agent.md
tools/                                        # new:plugin | new:agent | new:mcp | validate
```
