#!/usr/bin/env node
// Scaffold a custom agent. Writes the Copilot copy always; the Claude Code copy
// too, unless --copilot-only is passed.
// Usage: npm run new:agent -- <plugin> <kebab-agent-name> [--copilot-only] [description]
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const raw = process.argv.slice(2);
const copilotOnly = raw.includes('--copilot-only');
const args = raw.filter((a) => a !== '--copilot-only');
const [plugin, name, ...rest] = args;
const description = rest.join(' ') || `${name} agent`;

if (!plugin || !name || !/^[a-z0-9][a-z0-9-]*$/.test(name)) {
  console.error('Usage: npm run new:agent -- <plugin> <kebab-agent-name> [--copilot-only] [description]');
  process.exit(1);
}
const pdir = join(process.cwd(), 'plugins', plugin);
if (!existsSync(pdir)) { console.error(`No such plugin: ${pdir}. Run new:plugin first.`); process.exit(1); }

const body = `# ${name}

You are the ${name} agent. Replace this with the agent's role, process, and output format.

## Process
1. ...

## Output
...
`;

// --- Copilot copy: tools are NAMESPACED. See:
// https://code.visualstudio.com/docs/agents/reference/tools-reference
const copilotFm = `---
name: ${name}
description: ${description}
# 'target' is OMITTED on purpose so the agent is available in BOTH the VS Code Copilot
# picker and the GitHub Copilot CLI/app. Only set target: vscode | github-copilot to
# restrict it — VERIFY which value maps to the VS Code chat picker before narrowing.
# Pick namespaced tools, e.g. ['search/codebase', 'edit', 'execute/runInTerminal', '<mcp-server>/*']
tools: ['search/codebase', 'edit']
# model: optional — a single model name (string) or a prioritized array
---

`;
const cdir = join(pdir, 'com.github.copilot', 'agents');
mkdirSync(cdir, { recursive: true });
const cfile = join(cdir, `${name}.agent.md`);
if (existsSync(cfile)) { console.error(`Agent already exists: ${cfile}`); process.exit(1); }
writeFileSync(cfile, copilotFm + body);

if (!copilotOnly) {
  // --- Claude Code copy. VERIFY the correct in-plugin agent path for the current
  // Claude Code build (this pre-1.0 convention used a plugin-root agents/ folder).
  const claudeFm = `---
name: ${name}
description: ${description}
tools: Read, Grep, Glob
---

`;
  const adir = join(pdir, 'agents');
  mkdirSync(adir, { recursive: true });
  writeFileSync(join(adir, `${name}.agent.md`), claudeFm + body);
}

console.log(`Created agent '${name}' in plugin '${plugin}'${copilotOnly ? '' : ' (Copilot + Claude copies)'}.`);
console.log(`Edit tools/model/body in ${cfile}`);
