# Architecture: media-insight-engine on Kubernetes

## What runs where
```
namespace vault                         namespace mie-<env>
┌──────────────────────────┐           ┌───────────────────────────────────────────────────────────┐
│ vault-0 (dev mode)       │◀── login ─┤ server  (Deployment, 1)   + vault-agent sidecar           │
│  KV  secret/mie/<env>/*  │  issue    │   SA mie-server  ── TLS client cert (CN=mie) ──┐          │
│  PKI pki/ (root CA)      │◀──────────┤ postgres (StatefulSet, 1) + vault-agent sidecar│          │
│  auth/kubernetes         │           │   SA mie-postgres ◀─────── hostssl cert ───────┘          │
│ vault-agent-injector     │           │ client  (Deployment, nginx) ── /api/* ──▶ svc "server"    │
│  (mutating webhook)      │           │ Ingress mie-<env>.local ──▶ svc client                     │
└──────────────────────────┘           └───────────────────────────────────────────────────────────┘
```

## How a pod gets its secrets (Vault Agent Injector)
1. A pod annotated `vault.hashicorp.com/agent-inject: "true"` is changed by the injector webhook at
   admission. It gains a `vault-agent-init` container and a `vault-agent` sidecar.
2. The agent logs in to Vault's **Kubernetes auth** with the pod's service-account token. Vault checks the
   token with the Kubernetes API, including its audience, and maps `mie-server` in `mie-dev` to role
   `mie-dev-server` and policy `mie-dev-server`. There's no token file and no shared secret.
3. The agent renders templates into `/vault/secrets/`, an in-memory volume shared with the app. The init
   container renders them before the app starts, and the sidecar keeps renewing them.

| Pod | File | From Vault | Used as |
|---|---|---|---|
| server | `app.env` | KV `secret/mie/<env>/app` (every key in `.env` except below) | `. /vault/secrets/app.env` before `uvicorn` |
| server | `db-client.pem` | PKI `pki/issue/mie-<env>-db-client`, CN=mie, **24h** | libpq `sslcert` and `sslkey` (cert, CA and key from one issue call) |
| server | `ca.crt` | `pki/cert/ca` | libpq `sslrootcert` (`sslmode=verify-full`) |
| postgres | `server.pem` | PKI `pki/issue/mie-<env>-db-server`, DNS `postgres[.mie-<env>.svc…]`, **30d** | `ssl_cert_file` and `ssl_key_file` |
| postgres | `ca.crt` | `pki/cert/ca` | `ssl_ca_file` (verifies client certs) |
| postgres | `pgpass` | KV `secret/mie/<env>/postgres` | `POSTGRES_PASSWORD_FILE` |

**Least privilege:** each policy ([charts/vault/policies](../charts/vault/policies)) reads only its own KV
path and can issue only its own certificate type. The PKI roles fix the allowed names, so the server can't
get a cert for `postgres`, and nothing can get one for another name. The API server never sees the
Postgres superuser password.

**Database login:** `pg_hba` ([manifests/configmaps/postgres-hba.yaml](../manifests/configmaps/postgres-hba.yaml))
only allows `hostssl`. The app logs in with its client certificate. Postgres maps the cert's CN `mie` to the
role `mie` and requires that the cert is signed by Vault's CA (`clientcert=verify-full`). The app also checks
the server certificate against the same CA, including the hostname.

**Renewal:** the agent renews the 24h client cert before it expires. libpq reads the cert files on every new
connection, and the app's pool recycles connections hourly, so new connections use the new cert with no
restart. Postgres reads its own certificate only at start (see the `ponytail:` note in
[deployments/postgres.yaml](../manifests/deployments/postgres.yaml)).

Docker Compose is different: there, the server fetches a long-lived cert from Vault KV itself
(`DB_AUTH=cert`, [server/app/secrets.py](../../server/app/secrets.py)). In Kubernetes it runs with
`DB_AUTH=password`, meaning "use `DATABASE_URL` as is", and the URL points libpq at the agent's files. The
app code is the same in both.

## Local (minikube) vs. production (e.g. EKS)
| | Here | Production |
|---|---|---|
| Vault | one pod, dev mode: in memory, root token, refilled by `deploy.sh` | HA cluster (raft storage, 3–5 pods), auto-unseal with a cloud KMS, audit log, no root token in use. Or HCP Vault |
| Root CA | generated inside Vault's `pki/` | an offline root plus an intermediate CA in Vault |
| Storage | minikube `standard` (hostPath) | the cluster default (EBS gp3) |
| Ingress | minikube ingress addon + `minikube tunnel` / port-forward | AWS Load Balancer Controller or ingress-nginx + DNS + TLS |
| Postgres | StatefulSet with client-cert auth | the same, or CloudNativePG. **RDS/Aurora can't do client-cert auth**: there you'd use Vault's database secrets engine (dynamic passwords) or RDS IAM auth |
| Images | dev: built in minikube; test/prod: pinned GHCR SHAs | pinned SHAs, rolled out by GitOps (Argo CD / Flux) |
| Server replicas | 1 (ingest jobs run in-process) | 1, until ingest moves to a separate worker |
