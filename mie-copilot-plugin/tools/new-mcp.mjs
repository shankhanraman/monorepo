#!/usr/bin/env node
// Add an MCP server to a plugin. Bundled stdio server by default, or --http <url>.
// Usage: npm run new:mcp -- <plugin> <kebab-server-name> [--http <url>]
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const args = process.argv.slice(2);
const httpIdx = args.indexOf('--http');
const httpUrl = httpIdx !== -1 ? args[httpIdx + 1] : null;
const positional = args.filter((a, i) => {
  if (a === '--http') return false;
  if (httpIdx !== -1 && i === httpIdx + 1) return false;
  return true;
});
const [plugin, name] = positional;

if (!plugin || !name || !/^[a-z0-9][a-z0-9-]*$/.test(name)) {
  console.error('Usage: npm run new:mcp -- <plugin> <kebab-server-name> [--http <url>]');
  process.exit(1);
}
const pdir = join(process.cwd(), 'plugins', plugin);
if (!existsSync(pdir)) { console.error(`No such plugin: ${pdir}. Run new:plugin first.`); process.exit(1); }

const mpath = join(pdir, 'mcp.json');
const mcp = existsSync(mpath) ? JSON.parse(readFileSync(mpath, 'utf8')) : { mcpServers: {} };
mcp.mcpServers ||= {};
if (mcp.mcpServers[name]) { console.error(`Server '${name}' already exists in ${mpath}`); process.exit(1); }

if (httpUrl) {
  mcp.mcpServers[name] = { type: 'http', url: httpUrl };
} else {
  const sdir = join(pdir, 'servers', name);
  mkdirSync(sdir, { recursive: true });
  writeFileSync(join(sdir, 'index.mjs'), stdioServerTemplate(name));
  // ${CLAUDE_PLUGIN_ROOT} is injected by VS Code and resolves to the plugin root.
  mcp.mcpServers[name] = {
    command: 'node',
    args: ['${CLAUDE_PLUGIN_ROOT}/servers/' + name + '/index.mjs'],
  };
}
writeFileSync(mpath, JSON.stringify(mcp, null, 2) + '\n');
console.log(`Added MCP server '${name}' to plugin '${plugin}'.`);
if (!httpUrl) console.log(`Edit the server + its tools in plugins/${plugin}/servers/${name}/index.mjs`);

function stdioServerTemplate(serverName) {
  return `#!/usr/bin/env node
// Minimal MCP stdio server (reference skeleton) — zero dependencies.
// It speaks newline-delimited JSON-RPC 2.0 over stdio and exposes one 'echo' tool.
// For anything real, prefer the official MCP SDK and VERIFY the current protocol
// version at https://modelcontextprotocol.io .
import { createInterface } from 'node:readline';

const PROTOCOL_VERSION = '2025-06-18'; // VERIFY against the current MCP spec.
const SERVER_NAME = '${serverName}';
const TOOLS = [
  {
    name: 'echo',
    description: 'Echo back the provided text.',
    inputSchema: {
      type: 'object',
      properties: { text: { type: 'string' } },
      required: ['text'],
    },
  },
];

function send(msg) { process.stdout.write(JSON.stringify(msg) + '\\n'); }
function ok(id, result) { send({ jsonrpc: '2.0', id, result }); }
function fail(id, code, message) { send({ jsonrpc: '2.0', id, error: { code, message } }); }

const rl = createInterface({ input: process.stdin });
rl.on('line', (line) => {
  const text = line.trim();
  if (!text) return;
  let msg;
  try { msg = JSON.parse(text); } catch { return; }
  const { id, method, params } = msg;

  if (method === 'initialize') {
    ok(id, {
      protocolVersion: PROTOCOL_VERSION,
      capabilities: { tools: {} },
      serverInfo: { name: SERVER_NAME, version: '0.1.0' },
    });
  } else if (method === 'tools/list') {
    ok(id, { tools: TOOLS });
  } else if (method === 'tools/call') {
    const { name, arguments: a = {} } = params || {};
    if (name === 'echo') ok(id, { content: [{ type: 'text', text: String(a.text ?? '') }] });
    else fail(id, -32602, 'Unknown tool: ' + name);
  } else if (typeof method === 'string' && method.startsWith('notifications/')) {
    // notifications carry no id and expect no response
  } else if (id !== undefined) {
    fail(id, -32601, 'Method not found: ' + method);
  }
});
`;
}
