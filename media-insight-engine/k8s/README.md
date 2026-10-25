# media-insight-engine on Kubernetes (minikube)

Runs the app on a local minikube cluster shaped like production. The `.env` secrets live in **Vault**, and
the database login uses **short-lived TLS client certificates from Vault's PKI**. Each pod proves who it is
to Vault with its Kubernetes service account. Design: [docs/architecture.md](docs/architecture.md).

## Prerequisites
- Docker Desktop with **≥ 7 GB of RAM** (Settings → Resources)
- `minikube`, `kubectl`, `helm`, and bash (macOS/Linux, or Git Bash on Windows)
- `media-insight-engine/.env` with `ANTHROPIC_API_KEY` and `POSTGRES_PASSWORD` (copy `.env.example`)

## Quickstart (dev)
```bash
cd media-insight-engine/k8s
scripts/minikube-up.sh      # minikube profile "mie" (4 CPU / 6 GB / 40 GB) + ingress + Vault
scripts/deploy.sh dev       # build images in minikube (~15 min the first time) → Vault → apply → wait
kubectl --context mie -n mie-dev port-forward svc/client 8080:80
```
Open **http://localhost:8080**. Health: `curl localhost:8080/api/health` → `{"status":"ok","whisper":"cpu"}`.

Sync a collection: the **Sync** button in the app, or
`kubectl --context mie -n mie-dev exec deploy/server -c server -- sh -c '. /vault/secrets/app.env && python -m app.sync yale'`.

**Git Bash on Windows:** it rewrites arguments that start with `/` (such as `/vault/secrets/...`) into
Windows paths. Prefix `kubectl exec` commands that use container paths with `MSYS_NO_PATHCONV=1`. The scripts
don't need it.

## Day to day
| Change | Do |
|---|---|
| a collection YAML, lens, prompt or golden file | `scripts/deploy.sh dev` (the server restarts only if those files changed) |
| server or client code | `scripts/deploy.sh dev` (rebuilds the `:dev` images), then `kubectl --context mie -n mie-dev rollout restart deploy/server deploy/client` |
| a secret in `.env` | `scripts/deploy.sh dev` (rewrites Vault), then restart the server: the agent re-renders, but the process read `app.env` at start |
| test / prod | set the image SHA in `overlays/<env>/kustomization.yaml`, then `GHCR_TOKEN=<read:packages PAT> scripts/deploy.sh test` ([ci-cd/README.md](ci-cd/README.md)) |
| Vault UI | `kubectl --context mie -n vault port-forward svc/vault-ui 8200` → http://localhost:8200/ui, token `root` |
| stop / start | `minikube -p mie stop` / `scripts/minikube-up.sh && scripts/deploy.sh dev` (dev-mode Vault is empty after a restart, and deploy refills it) |
| remove everything | `minikube delete -p mie` |

## Layout
| Path | What |
|---|---|
| `manifests/` | Kustomize **base**: namespace, service accounts, ConfigMaps, server / client / postgres, services, ingress |
| `overlays/{dev,test,prod}/` | per environment: namespace `mie-<env>`, images, sizes, ingress host, **Vault role + paths** (`vault-patch.yaml`) |
| `charts/vault/` | values for the HashiCorp Vault Helm chart, and the two Vault policies |
| `scripts/` | `minikube-up.sh`, `vault-bootstrap.sh <env>`, `deploy.sh <env>` |
| `ci-cd/` | how the GHCR images from GitHub Actions reach test/prod |
| `docs/` | architecture and secret/certificate flow |

`manifests/storage` and `manifests/crds` only hold a README: the Postgres volume comes from its
StatefulSet, and the Vault injector needs no CRDs.
