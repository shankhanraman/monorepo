# Helm Chart for Media Insight Engine — Design

**Date:** 2026-10-24
**Status:** Approved design, pending spec review

## Goal

Provide a Helm chart that deploys the full Media Insight Engine stack to a **local
Kubernetes dev cluster** (kind, with a `localhost:5000` registry), reproducing what
`docker compose up` gives today — including the Vault + mutual-TLS Postgres security
model. One `helm install` should yield a working stack.

Non-goals: production hardening, externalized/managed Postgres, HA, non-dev Vault,
TLS ingress. These are explicitly out of scope (local dev parity only).

## Current stack (from docker-compose.yml)

| Service     | Image                     | Role |
|-------------|---------------------------|------|
| `vault`     | hashicorp/vault:1.18      | Dev-mode (in-memory, auto-unsealed) secret store |
| `cert-init` | hashicorp/vault:1.18      | One-shot: generate CA/server/client certs, seed Vault, place PG certs |
| `db`        | pgvector/pgvector:pg17    | Postgres w/ mutual-TLS (`hostssl ... cert clientcert=verify-full`) |
| `server`    | built from `./server`     | FastAPI/uvicorn on :8003; fetches client cert + token from Vault at startup |
| `client`    | built from `./client`     | React/Vite UI; prod target is nginx proxying `/api/` → `http://server:8003/` |

Key facts the chart depends on:

- `server/app/secrets.py` checks the `VAULT_TOKEN` **env var first**, then
  `VAULT_TOKEN_FILE`. It reads the client bundle from Vault KV at
  `secret/data/<VAULT_DB_CERT_PATH>` (default path seed: `mie/db-client`) and writes
  it 0600 into `DB_CERT_DIR` (tmpfs).
- `client/nginx.conf` hard-codes upstream `http://server:8003/`, so the server
  Service **must be named `server`**.
- `config/`, `prompts/`, `golden/` are small (<75 KB total) read-only inputs mounted
  into the server; they are **not** baked into the server image.
- Postgres (uid 999 in the pgvector image) refuses to start unless it owns `server.key`
  and the key is `0600`.
- `cert-init.sh` currently seeds only the **client** bundle into Vault KV; the server
  cert/key is written to a shared volume.

## Target decisions (from brainstorming)

- Target: **local dev cluster** (kind + `localhost:5000` registry).
- App images: **built and pushed to `localhost:5000`** (`mie-server`, `mie-client`),
  parameterized in `values.yaml`, `imagePullPolicy: IfNotPresent`.
- Security: **faithful mTLS mirror** — Vault + cert-based Postgres auth preserved.
- Postgres server cert delivery: **Vault-as-source** — cert-init seeds a server bundle
  into Vault; the db pod's init-container pulls it. No kubectl/RBAC in the chart.

## Architecture

```
                 ┌────────────┐
                 │  cert-init  │  Job (normal, not a hook)
                 │   (vault)   │  1. gen CA + server + client certs
                 └─────┬──────┘  2. vault kv put secret/mie/db-client  (client bundle)
                       │         3. vault kv put secret/mie/db-server  (server bundle)
                       │         4. policy mie-db (read db-client) + mie-pg (read db-server)
                       │         5. token create -id=<fixed> for each policy
                       ▼
     ┌──────────┐   seeds    ┌──────────────────────────────┐
     │  vault   │◄───────────│ Vault KV (in-memory, dev)      │
     │ Deploy   │            └──────────────────────────────┘
     │ svc:8200 │                    ▲            ▲
     └──────────┘                    │            │ pull server bundle (init-container,
          ▲                          │            │ scoped token, write emptyDir 999:600)
          │ pull client bundle       │            │
          │ (app startup)            │       ┌────┴─────┐
     ┌────┴─────┐                    │       │   db     │ StatefulSet + PVC
     │  server  │ Deploy, svc:8003 ──┘       │ svc:5432 │ pg_hba.conf from ConfigMap
     │ (name=   │                            └──────────┘
     │  server) │ emptyDir(Memory) /run/mie-certs
     └────┬─────┘
          │ /api proxied by nginx
     ┌────┴─────┐
     │  client  │ Deploy, svc:80 (nginx prod)
     └──────────┘
```

### Startup ordering (no Helm hooks)

All four workloads are applied together. Ordering is enforced by **init-containers that
poll**, which tolerates the in-memory Vault being re-seeded after a restart:

1. `vault` Deployment starts; readiness probe = `vault status`.
2. `cert-init` Job runs once it can reach `vault:8200`; it generates certs and seeds
   Vault (both bundles, both policies, both fixed-id tokens). Idempotent: skips cert
   regen if a sentinel exists, but always re-seeds (Vault dev is in-memory).
3. `db` pod init-container polls Vault until `secret/mie/db-server` is readable, pulls
   `server.crt`/`server.key`/`ca.crt` into an `emptyDir`, `chown 999:999` +
   `chmod 600` the key, then the Postgres container starts against that emptyDir.
4. `server` pod init-container polls until `secret/mie/db-client` is readable and db is
   accepting connections; the app container then fetches its bundle at startup via
   `secrets.py` exactly as today.

### Token delivery (least-privilege parity, no RBAC)

- cert-init mints tokens with **fixed ids** chosen in `values.yaml`:
  `vault token create -id=<serverToken> -policy=mie-db -ttl=168h` and
  `vault token create -id=<dbToken> -policy=mie-pg -ttl=168h`.
- The Helm-created `Secret` (same one holding `ANTHROPIC_API_KEY` /
  `POSTGRES_PASSWORD`) carries those token ids. `server` and the db init-container
  receive them as `VAULT_TOKEN` env (picked up by `secrets.py:21` / the db-init script).
- No ServiceAccount/Role needed — Helm creates the Secret from values; cert-init only
  talks to Vault.

## Chart layout

```
media-insight-engine/charts/mie/
├── Chart.yaml
├── values.yaml
├── .helmignore
├── files/
│   ├── config/      # copied from ../../config  (make helm-sync)
│   ├── prompts/     # copied from ../../prompts
│   ├── golden/      # copied from ../../golden
│   ├── pg_hba.conf  # copied from ../../postgres/pg_hba.conf
│   └── cert-init-k8s.sh   # adapted cert-init script (Vault-only, dual bundle)
└── templates/
    ├── _helpers.tpl
    ├── secret.yaml              # ANTHROPIC_API_KEY, POSTGRES_PASSWORD, vault token ids
    ├── vault-deployment.yaml
    ├── vault-service.yaml
    ├── certinit-configmap.yaml  # cert-init-k8s.sh
    ├── certinit-job.yaml
    ├── db-configmap.yaml        # pg_hba.conf
    ├── db-statefulset.yaml      # + init-container pulling server bundle from Vault
    ├── db-service.yaml          # headless
    ├── app-config-configmap.yaml# config/ prompts/ golden/ via .Files.Glob
    ├── server-deployment.yaml   # + init-container polling Vault/db
    ├── server-service.yaml      # name: server
    ├── client-deployment.yaml
    ├── client-service.yaml
    ├── ingress.yaml             # gated: ingress.enabled=false
    └── NOTES.txt
```

ConfigMaps for `config/prompts/golden` are generated with `.Files.Glob` over `files/`.
Because Helm can only read files inside the chart dir, these are **copied** from the repo
roots into `files/`; a `make helm-sync` target keeps them in sync and documents the
duplication. Total size is well under the 1 MB ConfigMap limit.

## values.yaml (shape)

```yaml
images:
  registry: localhost:5000
  server: { repository: mie-server, tag: latest }
  client: { repository: mie-client, tag: latest }
  pullPolicy: IfNotPresent
vault:
  image: hashicorp/vault:1.18
  devRootToken: root
db:
  image: pgvector/pgvector:pg17
  storage: 2Gi
  database: mie
  user: mie
secrets:
  anthropicApiKey: ""        # required at install (--set or -f)
  postgresPassword: ""       # required at install
  vaultServerToken: mie-server-tok   # fixed id, policy mie-db
  vaultDbToken: mie-db-tok           # fixed id, policy mie-pg
ingress:
  enabled: false
  host: mie.local
```

## Secrets handling

`ANTHROPIC_API_KEY` and `POSTGRES_PASSWORD` are **never committed**. They are supplied at
install time (`--set secrets.anthropicApiKey=...` or a gitignored
`values-local.yaml`). `NOTES.txt` documents the required values. The `.helmignore`
excludes any `values-local.yaml`.

## Access

After `helm install`, `NOTES.txt` prints a `kubectl port-forward svc/<release>-client 8080:80`
command to reach the UI. An optional Ingress (disabled by default) is provided for users
with an ingress controller.

## Make targets

- `make helm-images` — build `mie-server` + `mie-client` (prod target) and push to
  `localhost:5000`.
- `make helm-sync` — copy `config/ prompts/ golden/ postgres/pg_hba.conf` into
  `charts/mie/files/`.
- `make helm-install` — `helm-sync` + `helm upgrade --install` with `values-local.yaml`.

## Known limitation (documented in NOTES.txt)

Vault runs in **dev mode (in-memory)**. If the Vault pod restarts, the seed is lost and
running `server`/`db` pods can no longer authenticate until cert-init re-runs. Recovery:
`kubectl delete job <release>-cert-init && helm upgrade ...` (or delete the cert-init Job
so it re-creates). This matches the dev-only scope; a persistent/HA Vault is out of scope.

## Testing

- `helm lint charts/mie`
- `helm template charts/mie` renders without error for default + `ingress.enabled=true`.
- End-to-end on kind: `make helm-images && make helm-install`, then verify
  `/api/collections` returns data through the client, confirming the full
  Vault → cert → mTLS → Postgres path works.
