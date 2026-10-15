#!/usr/bin/env bash
# mTLS service-mesh lab: macOS / Linux (bash 3.2+). Only Docker is needed on the host.
#
#   bash scripts/lab.sh                  setup: CA + certificates, start everything, run the scenarios
#   bash scripts/lab.sh test             run the scenarios again
#   bash scripts/lab.sh revoke <name>    revoke <name>'s certificate, reload the sidecars, show it's refused
#   bash scripts/lab.sh reissue <name>   give <name> a fresh certificate (e.g. after revoking)
#   bash scripts/lab.sh rotate           re-issue every certificate and reload the sidecars (zero app changes)
#   bash scripts/lab.sh down             stop everything (certificates stay in pki/out)
set -euo pipefail
cd "$(dirname "$0")/.."
run() { docker compose run --rm -q "$@"; }
IDENTITIES="users orders admin reporting"

wait_ready() {
  printf '    waiting for both sidecars'
  for _ in $(seq 1 30); do
    if run client call.py --as admin GET https://orders-app:8443/whoami >/dev/null 2>&1 \
      && run client call.py --as admin GET https://users-app:8443/whoami >/dev/null 2>&1; then echo " ok"; return 0; fi
    printf '.'; sleep 2
  done
  echo; echo "sidecars not ready: docker compose logs users-proxy orders-proxy" >&2; exit 1
}

reload_sidecars() { docker compose restart users-proxy orders-proxy >/dev/null; wait_ready; }   # Envoy reads certs + CRL at start

case "${1:-setup}" in
  setup)
    docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop, then re-run." >&2; exit 1; }
    echo "==> 1. Certificate authority and certificates (pki/out)"
    docker compose build -q pki client
    run pki init
    run pki ensure $IDENTITIES
    [ -f pki/out/foreign/admin.crt ] || run pki foreign
    echo "==> 2. Start apps + sidecars"
    docker compose up -d --build
    wait_ready
    echo "==> 3. Scenarios"
    run client scenarios.py;;
  test) shift; run client scenarios.py "$@";;
  revoke)
    name="${2:?usage: lab.sh revoke <name>}"
    run pki revoke "$name"; reload_sidecars
    run client scenarios.py --revoked "$name" || true
    echo; echo "To let $name in again with a NEW certificate: bash scripts/lab.sh reissue $name";;
  reissue)
    name="${2:?usage: lab.sh reissue <name>}"
    run pki issue "$name"; reload_sidecars
    run client call.py --as "$name" GET https://users-app:8443/whoami;;
  rotate)
    echo "==> Re-issuing every certificate (new keys, new serials)"
    for name in $IDENTITIES; do run pki issue "$name"; done
    reload_sidecars
    run client scenarios.py;;
  down) docker compose down;;
  *) sed -n '2,10p' "$0"; exit 2;;
esac
