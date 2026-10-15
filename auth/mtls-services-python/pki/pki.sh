#!/usr/bin/env bash
# Lab certificate authority. Runs inside the `pki` container (docker compose run --rm pki <command>),
# so the host needs no openssl. Everything is written to /pki/out (= ./pki/out, gitignored).
#
#   init                  create the lab CA (EC P-256, 1 year) + an empty CRL         (skips if it exists)
#   issue <name> [hours]  certificate for spiffe://lab.local/<name>, default 24 h     (always a fresh key)
#   ensure <names...>     issue only what's missing or expires within 1 h             (used by setup)
#   revoke <name>         revoke <name>'s current certificate and publish a new CRL
#   foreign               a CA we DON'T trust + an "admin" cert from it (for the untrusted-issuer demo)
#   show <name>           print subject, SPIFFE ID, serial and validity
set -euo pipefail
OUT=/pki/out; DB=$OUT/ca-db; TRUST_DOMAIN=lab.local
export SAN="${SAN:-DNS:unused}"   # the openssl config references $SAN; only "issue" sets a real value
mkdir -p "$OUT" "$DB"

cnf() {  # openssl ca config; SAN comes from $SAN
cat <<CNF
[ ca ]
default_ca = lab
[ lab ]
dir = $DB
database = $DB/index.txt
serial = $DB/serial
crlnumber = $DB/crlnumber
new_certs_dir = $DB
certificate = $OUT/ca.crt
private_key = $OUT/ca.key
default_md = sha256
policy = anything
unique_subject = no          # allow re-issuing (rotation) for the same name
copy_extensions = none
[ anything ]
commonName = supplied
[ svc ]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth, clientAuth   # services both accept and make mTLS calls
subjectAltName = \${ENV::SAN}
CNF
}

ensure_ca() { [ -f "$OUT/ca.crt" ] || { echo "no CA yet: run 'init' first" >&2; exit 1; }; }

gencrl() {
  # 30 days so a lab left alone doesn't break: an expired CRL makes Envoy reject every certificate.
  openssl ca -config <(cnf) -gencrl -crldays 30 -out "$OUT/crl.pem" 2>/dev/null
}

case "${1:-}" in
  init)
    if [ -f "$OUT/ca.crt" ]; then echo "CA exists: $OUT/ca.crt"; exit 0; fi
    openssl ecparam -name prime256v1 -genkey -noout -out "$OUT/ca.key"
    openssl req -x509 -new -key "$OUT/ca.key" -days 365 -subj "/O=Lab/CN=Lab Mesh CA" \
      -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -out "$OUT/ca.crt"
    : > "$DB/index.txt"; echo 1000 > "$DB/serial"; echo 1000 > "$DB/crlnumber"
    gencrl
    echo "created lab CA: $OUT/ca.crt (+ empty CRL)";;

  issue)
    ensure_ca; name="${2:?name}"; hours="${3:-24}"
    start=$(date -u -d "@$(( $(date +%s) - 300 ))" +%Y%m%d%H%M%SZ)          # 5 min back: tolerate clock skew
    end=$(date -u -d "@$(( $(date +%s) + hours * 3600 ))" +%Y%m%d%H%M%SZ)
    openssl ecparam -name prime256v1 -genkey -noout -out "$OUT/$name.key"
    openssl req -new -key "$OUT/$name.key" -subj "/O=Lab/CN=$name" -out "$OUT/$name.csr"
    # SPIFFE ID = the identity. DNS names only so clients can verify the server's hostname.
    SAN="URI:spiffe://$TRUST_DOMAIN/$name,DNS:$name-app,DNS:localhost" \
      openssl ca -batch -config <(cnf) -extensions svc -startdate "$start" -enddate "$end" \
      -in "$OUT/$name.csr" -out "$OUT/$name.crt" 2>/dev/null
    rm -f "$OUT/$name.csr"
    chmod 644 "$OUT/$name.key"   # ponytail: lab only, so the non-root envoy user can read it; real meshes keep keys in memory (SDS)
    echo "issued $name: spiffe://$TRUST_DOMAIN/$name, serial $(openssl x509 -in "$OUT/$name.crt" -noout -serial | cut -d= -f2), valid ${hours}h";;

  ensure)
    ensure_ca; shift
    for name in "$@"; do
      if [ -f "$OUT/$name.crt" ] && openssl x509 -in "$OUT/$name.crt" -noout -checkend 3600 >/dev/null; then
        echo "ok: $name (valid > 1 h)"
      else "$0" issue "$name"; fi
    done;;

  revoke)
    ensure_ca; name="${2:?name}"
    openssl ca -config <(cnf) -revoke "$OUT/$name.crt" 2>/dev/null
    gencrl
    echo "revoked $name (serial $(openssl x509 -in "$OUT/$name.crt" -noout -serial | cut -d= -f2)); new CRL written. Restart the sidecars to load it.";;

  foreign)
    F=$OUT/foreign; mkdir -p "$F"
    openssl ecparam -name prime256v1 -genkey -noout -out "$F/ca.key"
    openssl req -x509 -new -key "$F/ca.key" -days 30 -subj "/O=Not Us/CN=Foreign CA" -out "$F/ca.crt"
    openssl ecparam -name prime256v1 -genkey -noout -out "$F/admin.key"
    openssl req -new -key "$F/admin.key" -subj "/O=Not Us/CN=admin" -out "$F/admin.csr"
    openssl x509 -req -in "$F/admin.csr" -CA "$F/ca.crt" -CAkey "$F/ca.key" -CAcreateserial -days 1 \
      -extfile <(printf 'subjectAltName=URI:spiffe://%s/admin\nextendedKeyUsage=clientAuth\n' "$TRUST_DOMAIN") \
      -out "$F/admin.crt" 2>/dev/null
    rm -f "$F/admin.csr"; chmod 644 "$F/admin.key"
    echo "created a foreign CA and an 'admin' cert signed by it: $F/admin.crt (same SPIFFE ID, wrong issuer)";;

  show)
    name="${2:?name}"
    openssl x509 -in "$OUT/$name.crt" -noout -subject -serial -startdate -enddate -ext subjectAltName;;

  *) sed -n '2,12p' "$0"; exit 2;;
esac
