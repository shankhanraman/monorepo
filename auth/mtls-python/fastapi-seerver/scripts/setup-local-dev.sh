#!/usr/bin/env bash
# One-command setup for the mTLS lab (macOS/Linux/Git Bash). Needs Docker Desktop + openssl.
#
#   1. generate certs (CA + server + client) if missing
#   2. .env from .env.example if missing
#   3. docker compose up --build  ->  db + server (FastAPI, internal) + nginx (mTLS on :8443)
#
# Then test with curl (see README). FastAPI is not published; nginx :8443 is the only entry point.
set -euo pipefail
LAB="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$LAB"

echo "==> 1. certificates"
if [ -f certs/ca.crt ]; then echo "    already present (certs/ca.crt)"; else bash certs/make-certs.sh; fi

echo "==> 2. .env"
[ -f .env ] || cp .env.example .env

echo "==> 3. docker compose up --build"
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop and re-run."; exit 1; }
docker compose up --build -d

echo
echo "Up. Try it (curl uses OpenSSL on macOS/Linux):"
echo "  cd certs"
echo "  curl --cacert ca.crt https://localhost:8443/users/                                   # 200 (public read)"
echo "  curl --cacert ca.crt -X POST https://localhost:8443/users/ -H 'Content-Type: application/json' \\"
echo "       -d '{\"username\":\"a\",\"email\":\"a@example.com\"}'                                  # 401 (no client cert)"
echo "  curl --cacert ca.crt --cert client.crt --key client.key -X POST https://localhost:8443/users/ \\"
echo "       -H 'Content-Type: application/json' -d '{\"username\":\"a\",\"email\":\"a@example.com\"}'  # 201"
echo "  curl --cacert ca.crt --cert client.crt --key client.key https://localhost:8443/me        # {\"cn\":\"alice\"}"
echo
echo "Windows curl uses Schannel: add --ssl-no-revoke, and client certs need the Windows store or WSL/a container (see README)."
