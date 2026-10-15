#!/usr/bin/env bash
# One-command local setup for the API Key lab on macOS (bash 3.2+; also runs on Linux and Git Bash).
# No sudo needed. Safe to re-run: every step checks first and skips what is already done.
#
#   1. .env files + docker compose up      Postgres only (needs Docker Desktop running); no Keycloak
#   2. backend .venv + requirements.txt    then `alembic upgrade head` (tables + two seeded demo keys)
#   3. frontend npm install
#   4. start FastAPI (:8004) and Vite (:5177) in this terminal, open the browser; Ctrl+C stops both
#
# Usage:  bash scripts/setup-local-dev.sh             (from fastapi-seerver/)
#         bash scripts/setup-local-dev.sh --no-start  (steps 1-3 only)
set -euo pipefail

API_PORT=8004
WEB_PORT=5177

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(dirname "$BACKEND")"
FRONTEND="$LAB/frontend"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
skip() { printf '    \033[90malready done: %s\033[0m\n' "$1"; }
done_() { printf '    \033[32m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }
port_in_use() { curl -s -o /dev/null --max-time 2 "http://localhost:$1/"; }

step "1. Docker: Postgres"
for dir in "$LAB" "$BACKEND"; do
  if [ -f "$dir/.env" ]; then skip "$dir/.env"; else cp "$dir/.env.example" "$dir/.env"; done_ "created $dir/.env from .env.example"; fi
done
docker info >/dev/null 2>&1 || fail "Docker is not running. Start Docker Desktop, then re-run this script."
docker compose -f "$LAB/docker-compose.yml" up -d

step "2. Backend Python environment ($BACKEND/.venv)"
cd "$BACKEND"
if [ ! -d .venv ]; then
  if command -v uv >/dev/null; then uv venv --python 3.12 .venv
  else
    py=""; for c in python3.13 python3.12 python3.11 python3.10 python3; do
      if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then py=$c; break; fi
    done
    [ -n "$py" ] || fail "Python 3.10+ not found. Install uv (brew install uv) or Python 3.12."
    "$py" -m venv .venv
  fi
fi
BIN=.venv/bin; [ -d "$BIN" ] || BIN=.venv/Scripts   # macOS/Linux vs. Windows (Git Bash)
if command -v uv >/dev/null; then VIRTUAL_ENV="$BACKEND/.venv" uv pip install -q -r requirements.txt
else "$BIN/python" -m pip install -q -r requirements.txt; fi
done_ "backend dependencies installed"
# Waits for Postgres to accept connections, then creates tables and seeds the two demo keys.
for _ in $(seq 1 30); do "$BIN/python" -c "import psycopg,os; psycopg.connect(os.environ.get('PGTEST','')) if False else None" 2>/dev/null; "$BIN/alembic" upgrade head 2>/dev/null && break; sleep 2; done
"$BIN/alembic" upgrade head
done_ "database tables + seeded demo keys up to date (alembic)"

step "3. Frontend packages"
(cd "$FRONTEND" && npm install --no-fund --no-audit)
done_ "frontend dependencies installed"

if [ "${1:-}" = "--no-start" ]; then echo; done_ "Setup done (--no-start: servers not started)."; exit 0; fi

step "4. Start FastAPI and the frontend in this terminal"
trap 'trap - INT TERM EXIT; kill 0 2>/dev/null' INT TERM EXIT
if port_in_use $API_PORT; then skip "something already listens on :$API_PORT"
else (cd "$BACKEND" && "$BIN/fastapi" dev app/main.py --port $API_PORT) & done_ "FastAPI -> http://localhost:$API_PORT/docs"; fi
if port_in_use $WEB_PORT; then skip "something already listens on :$WEB_PORT"
else (cd "$FRONTEND" && npm run dev) & done_ "Vite -> http://localhost:$WEB_PORT"; fi
for _ in $(seq 1 30); do port_in_use $API_PORT && port_in_use $WEB_PORT && break; sleep 1; done
if command -v open >/dev/null; then open "http://localhost:$WEB_PORT"; elif command -v xdg-open >/dev/null; then xdg-open "http://localhost:$WEB_PORT"; fi

printf '\n\033[32mAll set. Open http://localhost:%s. Sign in with the seeded key:\033[0m\n' "$WEB_PORT"
printf '\033[32m  mial_live_demo_do_not_use_in_prod\033[0m\n'
printf '\033[33mFastAPI and Vite logs follow. Press Ctrl+C to stop both.\033[0m\n\n'
wait
