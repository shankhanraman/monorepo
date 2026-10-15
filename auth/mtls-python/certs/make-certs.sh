#!/usr/bin/env bash
# Generate a self-signed CA and, from it, a server cert (for nginx) and a client cert (for curl / the browser).
# Re-run any time; it overwrites. Requires openssl. Output stays in this folder (gitignored).
set -euo pipefail
cd "$(dirname "$0")"

# On Git Bash / MSYS, stop it rewriting the "/CN=..." subject into a Windows path. No effect elsewhere.
export MSYS_NO_PATHCONV=1

# Some Windows installs set OPENSSL_CONF to a path that doesn't exist. Use our own minimal config.
cat > openssl-min.cnf <<'EOF'
[req]
distinguished_name = dn
[dn]
EOF
export OPENSSL_CONF=openssl-min.cnf   # relative to this folder; no slashes for MSYS to rewrite

echo "==> CA"
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 365 -subj "/CN=mtls-lab-CA" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"

echo "==> server cert (CN=localhost, SAN localhost + 127.0.0.1)"
openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=localhost"
printf "subjectAltName=DNS:localhost,IP:127.0.0.1\n" > san.cnf
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -extfile san.cnf

echo "==> client cert (CN=alice)"
openssl req -newkey rsa:2048 -nodes -keyout client.key -out client.csr -subj "/CN=alice"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365

echo "==> client.p12 for browser import (password: changeit)"
openssl pkcs12 -export -inkey client.key -in client.crt -certfile ca.crt -out client.p12 -passout pass:changeit

rm -f server.csr client.csr ca.srl san.cnf openssl-min.cnf
echo "done: ca.crt, server.crt/key, client.crt/key, client.p12"
