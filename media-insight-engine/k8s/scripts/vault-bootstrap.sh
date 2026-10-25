#!/usr/bin/env bash
# Put everything one environment needs into Vault. Idempotent; scripts/deploy.sh runs it on every deploy,
# because dev-mode Vault forgets everything when its pod restarts.
#
#   scripts/vault-bootstrap.sh dev|test|prod
#
#   KV    secret/mie/<env>/app       every key in media-insight-engine/.env except the two below (server)
#         secret/mie/<env>/postgres  POSTGRES_PASSWORD (Postgres only; the server never sees it)
#   PKI   one root CA; roles mie-<env>-db-server (TTL ≤ 720h) and mie-<env>-db-client (CN=mie, ≤ 72h)
#   auth  kubernetes: role mie-<env>-server  → SA mie-server  in mie-<env> → policy mie-<env>-server
#                     role mie-<env>-postgres → SA mie-postgres in mie-<env> → policy mie-<env>-postgres
set -euo pipefail
PROFILE="${PROFILE:-mie}"
ENV="${1:-}"
case "$ENV" in dev|test|prod) ;; *) echo "usage: $0 dev|test|prod" >&2; exit 1 ;; esac
K8S="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$K8S/../.env"
# Audience in the pods' service-account tokens (minikube/kubeadm default; EKS uses https://kubernetes.default.svc)
SA_AUDIENCE="${SA_AUDIENCE:-https://kubernetes.default.svc.cluster.local}"
NS="mie-$ENV"
[ -f "$ENV_FILE" ] || { echo "No $ENV_FILE: copy .env.example to .env and fill it in" >&2; exit 1; }

# vault CLI inside the Vault pod (dev mode: root token). Secrets go in on stdin, never as arguments.
v() { kubectl --context "$PROFILE" -n vault exec -i vault-0 -- env VAULT_TOKEN=root vault "$@"; }

json_escape() { local s="${1//\\/\\\\}"; s="${s//\"/\\\"}"; printf '%s' "$s"; }

echo "== KV: secret/mie/$ENV/app and secret/mie/$ENV/postgres (from .env) =="
app="" pg_password=""
while IFS= read -r line || [ -n "$line" ]; do
  line="${line%$'\r'}"                                  # .env saved with Windows line endings
  case "$line" in ''|\#*) continue ;; esac
  key="${line%%=*}" val="${line#*=}"
  case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac
  val="$(printf '%s' "$val" | sed -E 's/[[:space:]]+#.*$//; s/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/')"   # inline comment, quotes
  case "$key" in
    POSTGRES_PASSWORD) pg_password="$val" ;;
    VAULT_DEV_ROOT_TOKEN_ID) ;;                          # Docker Compose's Vault only
    *) app+="${app:+,}\"$key\":\"$(json_escape "$val")\"" ;;
  esac
done < "$ENV_FILE"
[ -n "$pg_password" ] || { echo "POSTGRES_PASSWORD is empty in $ENV_FILE" >&2; exit 1; }
printf '{"data":{%s}}' "$app" | v write "secret/data/mie/$ENV/app" - >/dev/null
printf '{"data":{"POSTGRES_PASSWORD":"%s"}}' "$(json_escape "$pg_password")" | v write "secret/data/mie/$ENV/postgres" - >/dev/null

echo "== PKI: root CA + certificate roles =="
v secrets list | grep -q '^pki/' || v secrets enable pki >/dev/null
v secrets tune -max-lease-ttl=87600h pki >/dev/null
# Where clients find the CA and the revocation list (written into every issued cert)
v write pki/config/urls issuing_certificates="http://vault.vault.svc:8200/v1/pki/ca" \
  crl_distribution_points="http://vault.vault.svc:8200/v1/pki/crl" >/dev/null
if ! v read -field=certificate pki/cert/ca 2>/dev/null | grep -q "BEGIN CERTIFICATE"; then
  v write pki/root/generate/internal common_name="mie-local-ca" ttl=87600h >/dev/null
fi
v write "pki/roles/mie-$ENV-db-server" \
  allowed_domains="postgres,postgres.$NS.svc,postgres.$NS.svc.cluster.local" allow_bare_domains=true \
  server_flag=true client_flag=false max_ttl=720h >/dev/null
v write "pki/roles/mie-$ENV-db-client" \
  allowed_domains="mie" allow_bare_domains=true enforce_hostnames=false \
  server_flag=false client_flag=true ttl=24h max_ttl=72h >/dev/null

echo "== Kubernetes auth, policies, roles =="
v auth list | grep -q '^kubernetes/' || v auth enable kubernetes >/dev/null
# Running inside the cluster, Vault uses its own service account (token reviewer) and CA
v write auth/kubernetes/config kubernetes_host="https://kubernetes.default.svc:443" >/dev/null
for who in server postgres; do
  sed "s/__ENV__/$ENV/g" "$K8S/charts/vault/policies/$who.hcl" | v policy write "mie-$ENV-$who" - >/dev/null
  v write "auth/kubernetes/role/mie-$ENV-$who" \
    bound_service_account_names="mie-$who" bound_service_account_namespaces="$NS" \
    audience="$SA_AUDIENCE" policies="mie-$ENV-$who" ttl=1h >/dev/null
done

echo "Vault ready for $ENV."
