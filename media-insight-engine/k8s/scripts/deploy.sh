#!/usr/bin/env bash
# Deploy one environment to minikube (run scripts/minikube-up.sh once first).
#
#   scripts/deploy.sh dev                 # builds mie-server:dev / mie-client:dev inside minikube (~15 min the first time)
#   GHCR_TOKEN=... scripts/deploy.sh test # test/prod pull the pinned GHCR images; the token is needed while they're private
#
# Steps: (dev) build images → Vault bootstrap → kubectl apply -k overlay → config ConfigMaps → wait for rollout.
set -euo pipefail
PROFILE="${PROFILE:-mie}"   # minikube profile = kubectl context (scripts/minikube-up.sh)
ENV="${1:-}"
case "$ENV" in dev|test|prod) ;; *) echo "usage: $0 dev|test|prod" >&2; exit 1 ;; esac
K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$(cd "$K8S/.." && pwd)"
NS="mie-$ENV"
k() { kubectl --context "$PROFILE" "$@"; }

minikube -p "$PROFILE" status >/dev/null 2>&1 || { echo "minikube isn't running: scripts/minikube-up.sh" >&2; exit 1; }

if [ "$ENV" = dev ]; then
  echo "== Build images inside minikube =="
  minikube -p "$PROFILE" image build -t mie-server:dev "$APP/server"
  minikube -p "$PROFILE" image build -t mie-client:dev "$APP/client"   # last stage = "prod" (nginx)
  # minikube image build can exit 0 on a failed build, so check the images really exist
  for img in mie-server:dev mie-client:dev; do
    minikube -p "$PROFILE" image ls | grep -q "$img" || { echo "Image $img failed to build (see output above)" >&2; exit 1; }
  done
fi

PROFILE="$PROFILE" "$K8S/scripts/vault-bootstrap.sh" "$ENV"

echo "== Apply overlays/$ENV =="
k apply -k "$K8S/overlays/$ENV"

if [ "$ENV" != dev ] && [ -n "${GHCR_TOKEN:-}" ]; then
  k -n "$NS" create secret docker-registry ghcr-pull --docker-server=ghcr.io \
    --docker-username="${GHCR_USER:-shankhanraman}" --docker-password="$GHCR_TOKEN" \
    --dry-run=client -o yaml | k apply -f -
fi

echo "== Config, prompts, golden → ConfigMaps =="
for pair in collections:config/collections lenses:config/lenses prompts:prompts golden:golden; do
  k -n "$NS" create configmap "mie-${pair%%:*}" --from-file="$APP/${pair#*:}" \
    --dry-run=client -o yaml | k apply -f -
done
# Roll the server only when those files changed (same hash → no-op patch → no restart mid-transcription)
hash="$(cat "$APP"/config/*/* "$APP"/prompts/* "$APP"/golden/* | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-16)"
k -n "$NS" patch deployment server --type merge \
  -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"mie/config-hash\":\"$hash\"}}}}}" >/dev/null

echo "== Wait for rollout =="
k -n "$NS" rollout status statefulset/postgres --timeout=300s
k -n "$NS" rollout status deployment/server --timeout=600s
k -n "$NS" rollout status deployment/client --timeout=180s

cat <<EOF

Deployed $ENV. Open the app either way:
  kubectl --context $PROFILE -n $NS port-forward svc/client 8080:80   →  http://localhost:8080
  minikube -p $PROFILE tunnel  +  hosts entry "127.0.0.1 mie-$ENV.local"  →  http://mie-$ENV.local
Health:  curl http://localhost:8080/api/health    (expect "whisper": "cpu")
EOF
