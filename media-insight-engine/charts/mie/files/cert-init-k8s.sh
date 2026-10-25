#!/bin/sh
# Kubernetes cert bootstrap for certificate-based DB auth (adapted from scripts/cert-init.sh).
# Differs from the compose script: nothing is written to a shared volume. BOTH bundles are
# seeded into Vault KV, and the db pod's init-container pulls the server bundle itself
# (Vault-as-source). Vault dev mode is in-memory, so this must run on every (re)seed.
#
#   1. generate a CA + server cert (SAN=db,localhost) + client cert (CN=mie)
#   2. vault kv put secret/mie/db-client   (ca.crt, client.crt, client.key)  <- read by the app
#   3. vault kv put secret/mie/db-server   (ca.crt, server.crt, server.key)  <- read by the db init-container
#   4. policy mie-db (read db-client) + mie-pg (read db-server)
#   5. fixed-id tokens: SERVER_TOKEN (mie-db) for the app, DB_TOKEN (mie-pg) for the db init
set -eu

SRC=/tmp/certsrc
: "${SERVER_TOKEN:?set SERVER_TOKEN}"   # app token id (policy mie-db)
: "${DB_TOKEN:?set DB_TOKEN}"           # db-init token id (policy mie-pg)

command -v openssl >/dev/null 2>&1 || { echo "[cert-init] installing openssl"; apk add --no-cache openssl >/dev/null; }
mkdir -p "$SRC"

echo "[cert-init] generating CA + server + client certificates"
openssl req -x509 -nodes -newkey rsa:4096 -days 3650 \
  -keyout "$SRC/ca.key" -out "$SRC/ca.crt" -subj "/CN=mie-dev-ca"

printf "subjectAltName=DNS:db,DNS:localhost\n" > /tmp/san.ext
openssl req -new -nodes -newkey rsa:2048 -keyout "$SRC/server.key" -out /tmp/server.csr -subj "/CN=db"
openssl x509 -req -in /tmp/server.csr -CA "$SRC/ca.crt" -CAkey "$SRC/ca.key" -CAcreateserial \
  -out "$SRC/server.crt" -days 825 -extfile /tmp/san.ext

# Client CN must equal the Postgres role; cert auth maps CN -> DB user. -nodes = unencrypted key.
openssl req -new -nodes -newkey rsa:2048 -keyout "$SRC/client.key" -out /tmp/client.csr -subj "/CN=mie"
openssl x509 -req -in /tmp/client.csr -CA "$SRC/ca.crt" -CAkey "$SRC/ca.key" -CAcreateserial \
  -out "$SRC/client.crt" -days 825

echo "[cert-init] seeding Vault KV (db-client + db-server)"
vault kv put secret/mie/db-client \
  ca.crt=@"$SRC/ca.crt" \
  client.crt=@"$SRC/client.crt" \
  client.key=@"$SRC/client.key"
vault kv put secret/mie/db-server \
  ca.crt=@"$SRC/ca.crt" \
  server.crt=@"$SRC/server.crt" \
  server.key=@"$SRC/server.key"

echo "[cert-init] writing least-privilege policies"
vault policy write mie-db - <<'EOF'
path "secret/data/mie/db-client" {
  capabilities = ["read"]
}
EOF
vault policy write mie-pg - <<'EOF'
path "secret/data/mie/db-server" {
  capabilities = ["read"]
}
EOF

echo "[cert-init] minting fixed-id tokens"
# Revoke first so re-runs against the same (still-running) Vault don't hit duplicate-id errors.
vault token revoke "$SERVER_TOKEN" >/dev/null 2>&1 || true
vault token revoke "$DB_TOKEN" >/dev/null 2>&1 || true
vault token create -id="$SERVER_TOKEN" -policy=mie-db -ttl=168h -no-default-policy >/dev/null
vault token create -id="$DB_TOKEN"     -policy=mie-pg -ttl=168h -no-default-policy >/dev/null

echo "[cert-init] done"
