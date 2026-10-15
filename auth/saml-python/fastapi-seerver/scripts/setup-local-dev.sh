#!/usr/bin/env bash
# One-command setup for the SAML lab (macOS/Linux/Git Bash). Needs Docker Desktop.
#
#   1. .env from .env.example if missing
#   2. docker compose up --build  ->  db + keycloak (SAML IdP :8083) + server (SAML SP :8006)
#
# Then drive SSO in a browser (http://localhost:8006/saml/login) or with the script:
#   python ../saml_login_test.py        (from the repo's auth/ folder; needs `pip install requests`)
set -euo pipefail
LAB="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$LAB"

echo "==> 1. .env"
[ -f .env ] || cp .env.example .env

echo "==> 2. docker compose up --build (first run builds the SP image: xmlsec compile, ~2-3 min)"
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop and re-run."; exit 1; }
docker compose up --build -d

echo
echo "Up. Keycloak (IdP) : http://localhost:8083  (admin / admin, realm saml-lab)"
echo "    FastAPI (SP)   : http://localhost:8006   (/saml/login to start SSO, /saml/metadata)"
echo "First login waits for Keycloak to finish importing the realm (~30-60s on a cold start)."
echo
echo "Browser: open http://localhost:8006/saml/login  ->  sign in as alice / alice123."
echo "Tests (in the container, where xmlsec lives):  docker compose run --rm server python -m pytest -q"
