# API server (service account mie-server in namespace mie-__ENV__). __ENV__ is filled in by vault-bootstrap.sh.

# The app's .env secrets (ANTHROPIC_API_KEY, ...)
path "secret/data/mie/__ENV__/app" {
  capabilities = ["read"]
}

# Short-lived client certificate (CN=mie) for the Postgres TLS login
path "pki/issue/mie-__ENV__-db-client" {
  capabilities = ["update"]
}

# The CA, to verify the Postgres server certificate (sslmode=verify-full)
path "pki/cert/ca" {
  capabilities = ["read"]
}
