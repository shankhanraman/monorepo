# Media Insight Engine — Certificate-based DB Auth + Vault (design)

**Date:** 2026-10-21
**Status:** Approved, building

## Goal

Replace Postgres **password** auth with **mutual TLS (client-certificate) auth** for the
app→DB connection, and store the client cert/key + CA in **HashiCorp Vault** rather than
baking them into the image or committing them. Self-hosted docker-compose; no cloud dependency.

This is **Approach A** of the brainstorm: static certs stored in Vault's KV v2 engine, fetched
by the app at startup. Vault's PKI engine (dynamic issuance), AppRole, sealed/HA Vault, and
automated rotation are explicit next-steps, out of scope here.

## How cert auth works here

- Postgres runs with `ssl=on` and a server cert/key.
- `pg_hba.conf` authenticates the app **by its client certificate**: method `cert` with
  `clientcert=verify-full`. The client cert's **CN = `mie`** maps to the DB role `mie`; no
  password is sent.
- The app (psycopg/libpq) connects with `sslmode=verify-full` and three files on disk:
  `sslrootcert` (CA), `sslcert` (client cert), `sslkey` (client key).
- The app fetches those three PEMs from Vault at startup and writes them to a **tmpfs** path
  (RAM only), `0600`, then hands the paths to psycopg.

### pg_hba.conf — both rules kept (non-breaking)

The server enforces auth independent of any client flag, so to preserve the existing
non-Docker / `dev-mac` password workflow we keep two rules:

```
# TLS + client cert  → the app (cert auth, no password)
hostssl  mie  mie  all  cert  clientcert=verify-full
# non-TLS            → password fallback for dev-mac / local (must use sslmode=disable)
host     mie  mie  all  scram-sha-256
```

A TLS connection presenting a client cert matches the `hostssl` rule → cert auth. A non-TLS
connection (libpq `sslmode=disable`) matches the `host` rule → password. `dev-mac` and any
local non-Docker connection therefore must set `sslmode=disable` (Makefile updated).

## Architecture

### New docker-compose services

- **`vault`** — `hashicorp/vault:<pin>`, **dev mode** (in-memory, auto-unsealed), root token
  from `.env` (`VAULT_DEV_ROOT_TOKEN_ID`), bound to `127.0.0.1:8200`. Dev mode is local-only.
  **It loses all state on restart** — so seeding runs every boot (below).
- **`cert-init`** — one-shot bootstrap (`curlimages`-style small image or the vault image).
  Two responsibilities, split by idempotency:
  1. **Generate certs (idempotent, skip-if-present)** into the `pgcerts` + `shared-certs`
     volumes using `openssl`: a CA, a server cert (`SAN=DNS:db`), and a client cert
     (`CN=mie`). Client key generated with **`-nodes` (unencrypted)** — libpq must not block
     on a passphrase. Server key is `chown 999:999` + `chmod 600` so the Postgres process
     (uid 999 in the pgvector image) can read it and Postgres doesn't reject it as too-open.
     Certs live in **named volumes, never a Windows bind-mount** (host NTFS perms don't
     translate).
  2. **Seed Vault (runs unconditionally every boot)** — enable KV v2 at `secret/`, write the
     client cert/key + CA to `secret/mie/db-client`, and create a read-only **policy + scoped
     token** the app uses (least privilege: read that one path only).

### Dependency ordering

- `cert-init` `depends_on` `vault` with `condition: service_healthy`.
- `db` and `server` `depends_on` `cert-init` with `condition: service_completed_successfully`.
- `server` also waits on `db` `service_healthy`.

### App code (`server/app`)

- **`app/secrets.py`** *(new)* — Vault client over **httpx** (already a dependency; no new
  package). `ensure_db_certs() -> DbCertPaths`:
  - Reads `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_DB_CERT_PATH` (default `mie/db-client`),
    `DB_CERT_DIR` (default `/run/mie-certs`, a tmpfs).
  - KV v2 read: `GET {addr}/v1/secret/data/{path}` (note the **`data/` infix**); values are
    under `.data.data` in the JSON.
  - Writes `ca.crt`, `client.crt`, `client.key` into `DB_CERT_DIR` at `0600` (dir `0700`),
    returns their paths. Interface is intentionally swappable so a Vault-PKI backend can
    replace it later without touching callers.
- **`app/config.py`** — add `db_auth` (`"cert"` | `"password"`, default `"password"` so
  existing unit tests and local runs are unaffected unless opted in), `vault_addr`,
  `vault_token`, `vault_db_cert_path`, `db_cert_dir`. Add a helper that builds the psycopg
  **conninfo kwargs** (`sslmode`/`sslrootcert`/`sslcert`/`sslkey`) when `db_auth == "cert"`.
- **`app/db.py`** — when `db_auth == "cert"`, call `secrets.ensure_db_certs()` in `init_db()`
  **before** the first connect, and pass the ssl params to both the bootstrap
  `psycopg.connect(...)` and the `ConnectionPool(...)`. Password path unchanged otherwise.

### Build/verify in two phases (isolates failure modes)

mTLS and Vault fail in different ways; wiring both at once hides which broke.

1. **Phase 1 — mTLS only.** Certs mounted directly into both containers (`DB_AUTH=cert`,
   `secrets.py` reads from a local dir, not Vault). Prove: Postgres boots with `ssl=on`, and
   `/health` connects with `sslmode=verify-full` + client cert.
2. **Phase 2 — add Vault.** Move the client cert/key + CA into Vault KV; `secrets.py` fetches
   at startup. Prove `/health` still green end-to-end.

## Error handling

Fail fast in the FastAPI `lifespan` (same pattern as the existing `WHISPER_DEVICE` check):
Vault unreachable / 403 / missing secret / unreadable or wrong-perm key → a clear startup
error before serving traffic. `verify-full` host must stay `db` (matches server cert SAN); the
conninfo host must not drift to `localhost`/`127.0.0.1` for the containerized app.

## Testing

- **Pure (no Docker, default):** `secrets.py` write logic — mock the httpx KV response, assert
  `ca.crt`/`client.crt`/`client.key` written `0600` and paths returned; assert a 403/ missing
  secret raises a clear error. Conninfo builder — ssl params present iff `db_auth == "cert"`.
  All gated so the default suite runs without Vault/Docker (consistent with the project's
  pure/contract split).
- **Contract (Docker):** `/health` succeeds over mTLS end-to-end.

## Security notes

- Keys live in **RAM (tmpfs)**, never on disk in the app container, never in the image, never
  committed. Generated cert dirs + `.env` are gitignored.
- App's Vault token is **read-only on one path** (least privilege).
- **Dev-mode Vault is local-only.** Production would need a sealed, persistent, auto-unsealed
  Vault — documented as a next-step, not built here.

## Verification

Static (runnable without Docker, all passing):
- `pytest tests/test_secrets.py` — bundle written, `0600` key (POSIX), missing-key / 403 / no-token errors.
- `pytest tests/test_config.py tests/test_contract.py` — config + OpenAPI contract unaffected.
- `app.db` / `app.secrets` import clean; `db_auth` defaults to `password` (no behavior change unless opted in).
- `docker compose config` valid; `sh -n scripts/cert-init.sh` clean.

Live end-to-end (run when Docker Desktop is up):
1. `cp .env.example .env` and set `ANTHROPIC_API_KEY`, `POSTGRES_PASSWORD`, `VAULT_DEV_ROOT_TOKEN_ID`.
2. `docker compose up --build -d`
3. `docker compose logs cert-init` → shows cert generation + `vault kv put` + token minted.
4. `curl -s http://localhost:8003/health` → `{"status":"ok",...}` proves the app connected over mTLS.
5. Negative check: `docker compose exec db psql "postgresql://mie:$POSTGRES_PASSWORD@localhost/mie?sslmode=require"`
   should be **rejected** (no client cert) — confirms password-over-TLS is off; only `cert` works.

## Out of scope (documented next steps)

Vault **PKI** dynamic issuance (Approach B), **AppRole** instead of a static token, sealed/HA
Vault with auto-unseal + persistent storage, and automated certificate rotation.
