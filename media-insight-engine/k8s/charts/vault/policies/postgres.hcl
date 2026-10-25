# Postgres (service account mie-postgres in namespace mie-__ENV__). __ENV__ is filled in by vault-bootstrap.sh.

# POSTGRES_PASSWORD (superuser password for initdb and admin logins over TLS). Kept apart from the app's
# secrets so the API server never sees it.
path "secret/data/mie/__ENV__/postgres" {
  capabilities = ["read"]
}

# Postgres server certificate (DNS: postgres, postgres.mie-__ENV__.svc[.cluster.local])
path "pki/issue/mie-__ENV__-db-server" {
  capabilities = ["update"]
}

# The CA, to verify client certificates (clientcert=verify-full)
path "pki/cert/ca" {
  capabilities = ["read"]
}
