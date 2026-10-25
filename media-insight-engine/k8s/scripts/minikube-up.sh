#!/usr/bin/env bash
# Start minikube with room for the app, enable ingress, and install Vault (with the Agent Injector).
# Safe to re-run (e.g. after a reboot). macOS / Linux / Git Bash on Windows.
#
#   scripts/minikube-up.sh                       # profile "mie": 4 CPUs, 6 GB: Vault + one environment
#   CPUS=6 MEMORY=14336 scripts/minikube-up.sh   # dev + test + prod side by side (Docker needs that much RAM)
# Own minikube profile (and kubectl context) "mie", so other minikube clusters are left alone.
# CPUS/MEMORY only apply when the profile is first created (minikube delete -p mie to resize).
set -euo pipefail
PROFILE="${PROFILE:-mie}"
K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for c in minikube kubectl helm docker; do
  command -v "$c" >/dev/null 2>&1 || { echo "Missing required command: $c" >&2; exit 1; }
done

echo "== minikube =="
if minikube -p "$PROFILE" status >/dev/null 2>&1; then
  echo "already running"
else
  # 40 GB disk: the server image alone is ~6 GB (Chromium + the 1.6 GB Whisper model)
  minikube start -p "$PROFILE" --cpus "${CPUS:-4}" --memory "${MEMORY:-6144}" --disk-size 40g
fi
minikube -p "$PROFILE" addons enable ingress

echo "== Vault (hashicorp/vault chart, dev mode + agent injector) =="
helm repo add hashicorp https://helm.releases.hashicorp.com >/dev/null 2>&1 || true
helm repo update hashicorp >/dev/null
helm --kube-context "$PROFILE" upgrade --install vault hashicorp/vault --version 0.34.1 \
  --namespace vault --create-namespace -f "$K8S/charts/vault/values.yaml" --wait
kubectl --context "$PROFILE" -n vault wait --for=condition=Ready pod/vault-0 --timeout=180s

echo
echo "Ready. Next: scripts/deploy.sh dev"
