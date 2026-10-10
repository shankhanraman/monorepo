#!/usr/bin/env bash
# One-command local setup for the OAuth 2.0 BFF lab on macOS (bash 3.2+; also runs on Linux and Git Bash).
# No sudo needed. Safe to re-run: every step checks first and skips what is already done.
#
#   1. .env files + docker compose up      Postgres + Keycloak (needs Docker Desktop running)
#   2. wait for Keycloak                   realm bff-lab answers at http://localhost:8082
#   3. backend .venv + requirements.txt    then `alembic upgrade head` (creates the app's tables)
#   4. frontend npm install
#   5. start FastAPI (:8002) and Vite (:5175, proxies /api and /auth) in this terminal, open the browser; Ctrl+C stops both
#
# Usage:  bash scripts/setup-local-dev.sh             (from fastapi-seerver/)
#         bash scripts/setup-local-dev.sh --no-start  (steps 1-4 only)
set -euo pipefail

KEYCLOAK_URL="http://localhost:8082"
REALM="bff-lab"
API_PORT=8002
WEB_PORT=5175

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(dirname "$BACKEND")"
FRONTEND="$LAB/frontend"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
skip() { printf '    \033[90malready done: %s\033[0m\n' "$1"; }
done_() { printf '    \033[32m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }
# Something answers on http://localhost:<port>? curl tries IPv4 and IPv6 (Vite may listen on ::1 only).
port_in_use() { curl -s -o /dev/null --max-time 2 "http://localhost:$1/"; }
url_ok() { curl -sf -o /dev/null --max-time 3 "$1"; }

step "1. Docker: Postgres + Keycloak"
for dir in "$LAB" "$BACKEND"; do
  if [ -f "$dir/.env" ]; then skip "$dir/.env"; else cp "$dir/.env.example" "$dir/.env"; done_ "created $dir/.env from .env.example"; fi
done
docker info >/dev/null 2>&1 || fail "Docker is not running. Start Docker Desktop, then re-run this script."
docker compose -f "$LAB/docker-compose.yml" up -d

step "2. Wait for Keycloak (first start imports realm $REALM)"
discovery="$KEYCLOAK_URL/realms/$REALM/.well-known/openid-configuration"
for _ in $(seq 1 60); do url_ok "$discovery" && break; sleep 3; done
url_ok "$discovery" || fail "Keycloak not ready at $discovery. Check: docker compose logs keycloak"
done_ "Keycloak ready at $KEYCLOAK_URL (admin console: admin / admin)"

step "3. Backend Python environment ($BACKEND/.venv)"
cd "$BACKEND"
if [ ! -d .venv ]; then
  if command -v uv >/dev/null; then uv venv --python 3.12 .venv
  else
    py=""; for c in python3.13 python3.12 python3.11 python3.10 python3; do
      if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then py=$c; break; fi
    done
    [ -n "$py" ] || fail "Python 3.10+ not found. Install uv (brew install uv) or Python 3.12 (brew install python@3.12)."
    "$py" -m venv .venv
  fi
fi
BIN=.venv/bin; [ -d "$BIN" ] || BIN=.venv/Scripts   # macOS/Linux vs. Windows (Git Bash)
if command -v uv >/dev/null; then VIRTUAL_ENV="$BACKEND/.venv" uv pip install -q -r requirements.txt
else "$BIN/python" -m pip install -q -r requirements.txt; fi
done_ "backend dependencies installed"
"$BIN/alembic" upgrade head
done_ "database tables up to date (alembic)"

step "4. Frontend packages"
(cd "$FRONTEND" && npm install --no-fund --no-audit)
done_ "frontend dependencies installed"

if [ "${1:-}" = "--no-start" ]; then echo; done_ "Setup done (--no-start: servers not started)."; exit 0; fi

step "5. Start FastAPI and the frontend in this terminal"
# Ctrl+C (or any exit) stops everything this script started, including fastapi dev's reloader child.
trap 'trap - INT TERM EXIT; kill 0 2>/dev/null' INT TERM EXIT
if port_in_use $API_PORT; then skip "something already listens on :$API_PORT"
else (cd "$BACKEND" && "$BIN/fastapi" dev app/main.py --port $API_PORT) & done_ "FastAPI starting -> http://localhost:$API_PORT/docs"; fi
if port_in_use $WEB_PORT; then skip "something already listens on :$WEB_PORT"
else (cd "$FRONTEND" && npm run dev) & done_ "Vite starting -> http://localhost:$WEB_PORT"; fi
for _ in $(seq 1 30); do port_in_use $API_PORT && port_in_use $WEB_PORT && break; sleep 1; done
if command -v open >/dev/null; then open "http://localhost:$WEB_PORT"            # macOS
elif command -v xdg-open >/dev/null; then xdg-open "http://localhost:$WEB_PORT" # Linux
fi

printf '\n\033[32mAll set. The site opens as a guest: Sign in -> Log in (alice / alice123) or Sign in -> Register.\033[0m\n'
printf '\033[33mFastAPI and Vite logs follow below. Press Ctrl+C to stop both.\033[0m\n\n'
wait
