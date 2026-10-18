#!/usr/bin/env node
// Scaffold a new Agent Plugins 1.0 plugin and register it in the marketplace.
// Usage: npm run new:plugin -- <kebab-name> [description]
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const SCHEMA = 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json';
const [name, ...descParts] = process.argv.slice(2);
const description = descParts.join(' ') || `${name} plugin`;

if (!name || !/^[a-z0-9][a-z0-9-]*$/.test(name)) {
  console.error('Usage: npm run new:plugin -- <kebab-name> [description]');
  process.exit(1);
}

const root = process.cwd();
const pdir = join(root, 'plugins', name);
if (existsSync(pdir)) { console.error(`Plugin already exists: ${pdir}`); process.exit(1); }

mkdirSync(join(pdir, 'com.github.copilot', 'agents'), { recursive: true });
writeFileSync(
  join(pdir, 'plugin.json'),
  JSON.stringify({ $schema: SCHEMA, name, description, version: '0.1.0' }, null, 2) + '\n',
);
writeFileSync(join(pdir, 'mcp.json'), JSON.stringify({ mcpServers: {} }, null, 2) + '\n');

const mpath = join(root, '.claude-plugin', 'marketplace.json');
mkdirSync(join(root, '.claude-plugin'), { recursive: true });
const mp = existsSync(mpath)
  ? JSON.parse(readFileSync(mpath, 'utf8'))
  : { name: 'REPLACE-marketplace-name', owner: { name: 'REPLACE-owner' }, plugins: [] };
mp.plugins ||= [];
if (!mp.plugins.some((p) => p.name === name)) {
  mp.plugins.push({ name, source: `./plugins/${name}`, description });
  writeFileSync(mpath, JSON.stringify(mp, null, 2) + '\n');
}
console.log(`Created plugin '${name}'.`);
console.log(`Next: npm run new:agent -- ${name} <agent-name>`);
console.log(`      npm run new:mcp   -- ${name} <server-name>`);
