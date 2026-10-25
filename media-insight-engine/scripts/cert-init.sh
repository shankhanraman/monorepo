#!/bin/sh
# One-shot bootstrap for certificate-based DB auth.
#   1. generate a CA + server cert (SAN=db) + client cert (CN=mie)  — idempotent, skip if present
#   2. place server cert/key + CA in the Postgres volume (key chown 999:999, 0600)
#   3. seed the client cert/key + CA into Vault KV, and mint a read-only token for the app — every boot
# Runs on the hashicorp/vault (alpine) image as root. Vault dev mode is in-memory, so step 3 must
# run on every start even when step 1 is skipped.
set -eu

SRC=/certs/src          # persistent CA material (this container only)
PG=/certs/pg            # server certs for Postgres (pgcerts volume)
SHARED=/certs/shared    # vault token for the app (vaulttoken volume)
SECRET_PATH=secret/mie/db-client


#If OpenSSL is not installed, print a message and install it. Otherwise, do nothing.
command -v openssl >/dev/null 2>&1 || { echo "[cert-init] installing openssl"; apk add --no-cache openssl >/dev/null; }
mkdir -p "$SRC" "$PG" "$SHARED"


#check whether the certificates already exist
if [ ! -f "$SRC/ca.crt" ]; then
  echo "[cert-init] generating CA + server + client certificates"
  #Generate a new 4096-bit RSA private key and a self-signed CA certificate,
  # make the certificate valid for 10 years, and save both files in the directory specified by $SRC.
  openssl req -x509 -nodes -newkey rsa:4096 -days 3650 \
  #Make the trusted authority's certificate
    -keyout "$SRC/ca.key" -out "$SRC/ca.crt" -subj "/CN=mie-dev-ca"


#The names are called Subject Alternative Names (SANs). They help the application check that it's talking to the correct server.
  printf "subjectAltName=DNS:db,DNS:localhost\n" > /tmp/san.ext
  #Make the database's private key and request
  openssl req -new -nodes -newkey rsa:2048 -keyout "$SRC/server.key" -out /tmp/server.csr -subj "/CN=db"
  #Get the database's certificate signed
  openssl x509 -req -in /tmp/server.csr -CA "$SRC/ca.crt" -CAkey "$SRC/ca.key" -CAcreateserial \
    -out "$SRC/server.crt" -days 825 -extfile /tmp/san.ext

  ##Make the client's private key and request
  openssl req -new -nodes -newkey rsa:2048 -keyout "$SRC/client.key" -out /tmp/client.csr -subj "/CN=mie"
  #Get the client's certificate signed
  openssl x509 -req -in /tmp/client.csr -CA "$SRC/ca.crt" -CAkey "$SRC/ca.key" -CAcreateserial \
    -out "$SRC/client.crt" -days 825
else
  echo "[cert-init] certificates already present, reusing"
fi

echo "[cert-init] placing server certs for Postgres"
#Copy the server certificates into PostgreSQL
cp "$SRC/server.crt" "$SRC/server.key" "$SRC/ca.crt" "$PG/"
# Set PostgreSQL's file ownership and permissions
# 999:999 → Who owns the file?
# 600 → Who can access the file, and how?
# 644 → Who can read or modify the file?
chown 999:999 "$PG/server.key"
chmod 600 "$PG/server.key"
chmod 644 "$PG/server.crt" "$PG/ca.crt"


#uploads three certificate-related files into HashiCorp Vault,
# so your application can securely retrieve the credentials it needs to connect to PostgreSQL
echo "[cert-init] seeding Vault KV at $SECRET_PATH"
vault kv put "$SECRET_PATH" \
  ca.crt=@"$SRC/ca.crt" \
  client.crt=@"$SRC/client.crt" \
  client.key=@"$SRC/client.key"

  echo "[cert-init] writing least-privilege policy + token for the app"
  vault policy write mie-db - <<'EOF'
  path "secret/data/mie/db-client" {
    capabilities = ["read"]
  }
  EOF
  vault token create -policy=mie-db -ttl=168h -field=token > "$SHARED/
  vault-token"
  chmod 644 "$SHARED/vault-token"

  echo "[cert-init] done"