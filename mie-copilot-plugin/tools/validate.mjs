#!/usr/bin/env node
// Fitness check for the marketplace: manifests, agent frontmatter, MCP references.
// Usage: npm run validate
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const SCHEMA = 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json';
const root = process.cwd();
const errors = [];
const warnings = [];

const mpath = join(root, '.claude-plugin', 'marketplace.json');
if (!existsSync(mpath)) { errors.push('.claude-plugin/marketplace.json is missing'); report(); }

let mp;
try { mp = JSON.parse(readFileSync(mpath, 'utf8')); }
catch (e) { errors.push(`marketplace.json invalid JSON: ${e.message}`); report(); }

if (!Array.isArray(mp.plugins)) errors.push('marketplace.json: "plugins" must be an array');

for (const entry of mp.plugins || []) {
  const label = entry.source || entry.name || '(unnamed)';
  if (!entry.source) { errors.push(`marketplace entry '${entry.name}' has no "source"`); continue; }
  const pdir = join(root, entry.source);
  if (!existsSync(pdir)) { errors.push(`plugin source missing: ${entry.source}`); continue; }

  // plugin.json
  const pj = join(pdir, 'plugin.json');
  if (!existsSync(pj)) errors.push(`${label}/plugin.json missing`);
  else {
    let j = null;
    try { j = JSON.parse(readFileSync(pj, 'utf8')); }
    catch (e) { errors.push(`${label}/plugin.json invalid JSON: ${e.message}`); }
    if (j) {
      if (j.$schema !== SCHEMA) warnings.push(`${label}/plugin.json $schema is not the Agent Plugins 1.0 URL`);
      if (!j.name) errors.push(`${label}/plugin.json missing "name"`);
    }
  }

  // Copilot agents
  const cadir = join(pdir, 'com.github.copilot', 'agents');
  if (existsSync(cadir)) {
    for (const f of readdirSync(cadir).filter((x) => x.endsWith('.agent.md'))) {
      const fm = frontmatter(readFileSync(join(cadir, f), 'utf8'));
      if (fm === null) errors.push(`${label}/com.github.copilot/agents/${f}: missing YAML frontmatter`);
      else if (/\b(Bash|Read|Grep|Glob|Write|Edit)\b/.test(fm.tools || ''))
        warnings.push(`${label}/com.github.copilot/agents/${f}: uses Claude-style tool names; Copilot tools are namespaced (e.g. search/codebase, edit)`);
    }
  }

  // MCP config (mcp.json preferred; .mcp.json accepted)
  const mfile = existsSync(join(pdir, 'mcp.json'))
    ? join(pdir, 'mcp.json')
    : (existsSync(join(pdir, '.mcp.json')) ? join(pdir, '.mcp.json') : null);
  if (mfile) {
    let m = null;
    try { m = JSON.parse(readFileSync(mfile, 'utf8')); }
    catch (e) { errors.push(`${label} MCP config invalid JSON: ${e.message}`); }
    for (const [sname, s] of Object.entries((m && m.mcpServers) || {})) {
      if (!s.command && !s.url) errors.push(`${label} MCP server '${sname}' has neither "command" (stdio) nor "url" (http)`);
      for (const ref of [s.command, ...(s.args || [])].filter((x) => typeof x === 'string')) {
        const mm = ref.match(/\$\{CLAUDE_PLUGIN_ROOT\}\/(.+)/);
        if (mm && !existsSync(join(pdir, mm[1])))
          errors.push(`${label} MCP server '${sname}' references a missing file: ${mm[1]}`);
      }
    }
  }
}

report();

function frontmatter(txt) {
  const norm = txt.replace(/\r\n/g, '\n');
  const m = norm.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return null;
  const obj = {};
  for (const line of m[1].split('\n')) {
    const mm = line.match(/^([a-zA-Z_-]+):\s*(.*)$/);
    if (mm) obj[mm[1]] = mm[2];
  }
  return obj;
}

function report() {
  for (const w of warnings) console.log(`WARN  ${w}`);
  for (const e of errors) console.log(`ERROR ${e}`);
  console.log(`\n${errors.length} error(s), ${warnings.length} warning(s).`);
  process.exit(errors.length ? 1 : 0);
}
