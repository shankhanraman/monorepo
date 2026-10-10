#!/usr/bin/env bash
# One-command local setup for the Kerberos -> Keycloak -> FastAPI lab on macOS (bash 3.2+).
# Safe to re-run: every step checks first and skips what is already done.
#
#   macOS machine steps (asks for your Mac password once, for sudo):
#     M1. /etc/hosts: keycloak.lab.local, kdc.lab.local    Kerberos tickets are tied to this hostname
#     M2. /etc/krb5.conf from krb5.conf.mac               realm LAB.LOCAL, KDC on 127.0.0.1 (TCP)
#         (macOS has Kerberos built in: no MIT Kerberos to install. Any existing file is backed up first.)
#     M3. Chrome: allow Kerberos for keycloak.lab.local    (only if Chrome is installed and nothing is set yet)
#   Then:
#     1. .env files + docker compose up      Postgres + KDC + Keycloak + keycloak-init (needs Docker Desktop)
#     2. backend .venv + requirements.txt    then `alembic upgrade head`
#     3. frontend npm install
#     4. kinit <user>@LAB.LOCAL              asks for the Kerberos password (alice: alice123)
#     5. start FastAPI (:8000) and Vite (:5173) in this terminal, open the browser; Ctrl+C stops both
#
# Usage (from fastapi-seerver/):
#   bash scripts/setup-local-dev.sh                 # as alice
#   bash scripts/setup-local-dev.sh --user bob      # another Kerberos user
#   bash scripts/setup-local-dev.sh --no-start      # setup only, don't start the servers
# On Windows use setup-local-dev.ps1. On Linux the machine steps and kinit are skipped (see README).
set -euo pipefail

KC_USER="alice"; NO_START=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) KC_USER="$2"; shift 2;;
    --no-start) NO_START=1; shift;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

API_PORT=8000
WEB_PORT=5173
HOSTS_NAMES="keycloak.lab.local kdc.lab.local"

BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
LAB="$(dirname "$BACKEND")"
FRONTEND="$LAB/frontend"
COMPOSE="$LAB/docker-compose.yml"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
skip() { printf '    \033[90malready done: %s\033[0m\n' "$1"; }
done_() { printf '    \033[32m%s\033[0m\n' "$1"; }
note() { printf '    \033[33m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }
# Something answers on http://localhost:<port>? curl tries IPv4 and IPv6 (Vite may listen on ::1 only).
port_in_use() { curl -s -o /dev/null --max-time 2 "http://localhost:$1/"; }

IS_MAC=""; [ "$(uname -s)" = "Darwin" ] && IS_MAC=1

# --- macOS machine steps ------------------------------------------------------------------------
if [ -n "$IS_MAC" ]; then
  step "M1. /etc/hosts entries for $HOSTS_NAMES"
  if grep -qE '^[[:space:]]*127\.0\.0\.1[[:space:]].*keycloak\.lab\.local' /etc/hosts; then skip "/etc/hosts"
  else
    # Both IPv4 and IPv6: macOS treats *.local as Bonjour names, and an IPv4-only entry can stall lookups ~5 s.
    printf '127.0.0.1 %s\n::1 %s\n' "$HOSTS_NAMES" "$HOSTS_NAMES" | sudo tee -a /etc/hosts >/dev/null
    sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder 2>/dev/null || true
    done_ "added to /etc/hosts (DNS cache flushed)"
  fi

  step "M2. Kerberos client config (/etc/krb5.conf)"
  if [ -f /etc/krb5.conf ] && cmp -s "$LAB/krb5.conf.mac" /etc/krb5.conf; then skip "/etc/krb5.conf"
  else
    if [ -f /etc/krb5.conf ]; then
      backup="/etc/krb5.conf.backup-$(date +%Y%m%d%H%M%S)"
      sudo cp /etc/krb5.conf "$backup"
      note "your existing /etc/krb5.conf was saved as $backup (restore it when you're done with the lab)"
    fi
    sudo cp "$LAB/krb5.conf.mac" /etc/krb5.conf
    done_ "wrote /etc/krb5.conf (realm LAB.LOCAL, kdc tcp/127.0.0.1:88)"
  fi

  step "M3. Browser settings for Kerberos (SPNEGO)"
  if [ -d "/Applications/Google Chrome.app" ]; then
    current="$(defaults read com.google.Chrome AuthServerAllowlist 2>/dev/null || true)"
    if [ "$current" = "keycloak.lab.local" ]; then skip "Chrome AuthServerAllowlist"
    elif [ -z "$current" ]; then
      defaults write com.google.Chrome AuthServerAllowlist "keycloak.lab.local"
      done_ "Chrome: AuthServerAllowlist=keycloak.lab.local (quit and reopen Chrome to apply; check chrome://policy)"
    else note "Chrome already has AuthServerAllowlist='$current'; add keycloak.lab.local to it yourself"; fi
  fi
  note "Safari: uses the system Kerberos ticket, usually with no settings."
  note "Firefox: about:config -> network.negotiate-auth.trusted-uris = keycloak.lab.local (nothing else needed on macOS)."
else
  step "Machine setup skipped (not macOS)"
  note "On Windows use setup-local-dev.ps1. On Linux: add the /etc/hosts line, write /etc/krb5.conf (see README), run kinit."
fi

# --- lab -----------------------------------------------------------------------------------------
step "1. Docker: Postgres + KDC + Keycloak"
for dir in "$LAB" "$BACKEND"; do
  if [ -f "$dir/.env" ]; then skip "$dir/.env"; else cp "$dir/.env.example" "$dir/.env"; done_ "created $dir/.env from .env.example"; fi
done
docker info >/dev/null 2>&1 || fail "Docker is not running. Start Docker Desktop, then re-run this script."
docker compose -f "$COMPOSE" up -d --build
echo "    waiting for keycloak-init (turns on the Kerberos login step)..."
state=""
for _ in $(seq 1 60); do
  state="$(docker compose -f "$COMPOSE" ps -a keycloak-init --format '{{.State}} {{.ExitCode}}')"
  [ "$state" = "exited 0" ] && break; sleep 3
done
[ "$state" = "exited 0" ] || fail "keycloak-init did not finish (state: $state). Check: docker compose logs keycloak-init"
done_ "Keycloak ready at http://keycloak.lab.local:8080 (admin / admin)"

step "2. Backend Python environment ($BACKEND/.venv)"
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

step "3. Frontend packages"
(cd "$FRONTEND" && npm install --no-fund --no-audit)
done_ "frontend dependencies installed"

step "4. Kerberos ticket for $KC_USER@LAB.LOCAL"
if [ -z "$IS_MAC" ]; then note "skipped (not macOS): run kinit $KC_USER@LAB.LOCAL yourself"
elif (klist -s 2>/dev/null || klist -t 2>/dev/null) && klist 2>/dev/null | grep -q "$KC_USER@LAB.LOCAL"; then
  skip "valid ticket for $KC_USER"
else
  [ "$KC_USER" = "alice" ] && note "password is alice123"
  kinit "$KC_USER@LAB.LOCAL" || fail "kinit failed. Is the kdc container running (docker compose ps kdc)?"
  done_ "got a ticket-granting ticket (klist shows it)"
fi

if [ -n "$NO_START" ]; then echo; done_ "Setup done (--no-start: servers not started)."; exit 0; fi

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

printf '\n\033[32mAll set. The site opens as a guest: Sign in -> Log in signs you in as %s with no password prompt.\033[0m\n' "$KC_USER"
printf 'Check the service ticket afterwards: klist   (look for HTTP/keycloak.lab.local)\n'
printf '\033[33mFastAPI and Vite logs follow below. Press Ctrl+C to stop both.\033[0m\n\n'
wait
