# media-insight-engine Helm chart

Deploys the Admissions Media Insight Engine: the FastAPI server, the nginx client, and Postgres with
pgvector. Secrets and database certificates come **only from Vault**. The Vault Agent Injector writes the
`.env` secrets and short-lived TLS certificates (Vault PKI) into each pod, which logs in with its Kubernetes
service account. Postgres accepts only TLS client-certificate logins from the app.

## Install
```bash
helm repo add mie https://shankhanraman.github.io/monorepo
helm repo update
helm search repo mie
helm install mie mie/media-insight-engine -n mie-dev --create-namespace
kubectl -n mie-dev logs deployment/mie-media-insight-engine-server -c server
```

### Prerequisites (once per cluster / environment)
1. **Vault with the Agent Injector.** `helm install vault hashicorp/vault -n vault --create-namespace -f ../vault/values.yaml`,
   or `scripts/minikube-up.sh`, which also starts minikube.
2. **Vault data for the environment.** Run `scripts/vault-bootstrap.sh dev`. It stores your `.env` in Vault
   and creates the PKI and Kubernetes auth roles.
3. **Namespace `mie-<env>`.** The Vault roles are bound to it, and the chart refuses another namespace.
4. **Image pull secret** while the GHCR images are private: create `ghcr-pull` in the namespace and set
   `imagePullSecrets: [{name: ghcr-pull}]`.

## Values
| Key | Default | |
|---|---|---|
| `env` | `dev` | Vault environment: role `mie-<env>-*`, KV `secret/mie/<env>/*`, PKI roles `mie-<env>-db-*` |
| `server.image` / `client.image` | `ghcr.io/shankhanraman/mie-server` / `mie-client`, tag = `appVersion` | |
| `server.env` | `{WHISPER_DEVICE: cpu}` | non-secret settings (secrets come from Vault) |
| `server.resources` | 3 Gi request / 4 Gi limit | the Whisper model needs ~2 GB |
| `client.replicas` | `1` | |
| `postgres.storage` | `2Gi` | |
| `vault.clientCertTTL` / `serverCertTTL` | `24h` / `720h` | must not exceed the PKI roles' max |
| `ingress.enabled` / `host` / `className` | `true` / `mie-dev.local` / `nginx` | |
| `imagePullSecrets` | `[]` | |

Per-environment values: `overlays/{dev,test,prod}/values.yaml` in the repo.

## Notes
- **One release per namespace.** The Services are named `server`, `client` and `postgres`, because the
  client image proxies `/api` to `server:8003` and the PKI role only issues certificates for `postgres`.
- `config/`, `prompts/` and `golden/` ship inside the chart (as ConfigMaps). To change them, install from
  source after `scripts/chart-files.sh`, or publish a new chart version.
- Design and production differences: [docs/architecture.md](../../docs/architecture.md).
