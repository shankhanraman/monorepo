# mTLS service-to-service lab (certificate-based authentication, service-mesh style)

How big companies use certificates for authentication **between services**: every service has an **Envoy sidecar** that
- **requires a client certificate** from the company CA on every incoming connection (mutual TLS);
- **presents its own certificate** on every outgoing call;
- tells the app **who called**, as a SPIFFE ID (`spiffe://lab.local/orders`).

**The app code never touches a certificate.** This is what Istio, Linkerd, Consul and SPIRE do in production, scaled down to Docker Compose.

```
            mTLS (admin cert)                          mTLS (orders cert)
host/client ─────────────────► [envoy | orders-app] ─────────────────────► [envoy | users-app]
                                  sidecar  127.0.0.1                          sidecar  127.0.0.1
                                  :8443    :8000                              :8443    :8000
```

**New here? Read [GETTING-STARTED.md](GETTING-STARTED.md).** Design: [docs/architecture.md](docs/architecture.md) · flows: [docs/dataflow.md](docs/dataflow.md) · real-world mapping: [docs/production.md](docs/production.md).

## Quick start (only Docker needed, Windows or macOS)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\lab.ps1          # Windows
```
```bash
bash scripts/lab.sh                                               # macOS / Linux
```
It creates a lab CA and certificates, starts two services with sidecars, and runs the **scenario check**:

```
PASS  1. no client certificate                                  TLS refused
PASS  2. certificate from a foreign CA (same SPIFFE ID!)        TLS refused
PASS  3. admin: create user (users) + order (orders→users mTLS) users 201, orders 201
PASS  4. reporting: valid cert, read OK, write forbidden        GET 200, POST 403
PASS  5. reporting forges 'I am admin' header                   seen as 'reporting', write 403
PASS  6. bypass the sidecar (plain HTTP to the app port)        unreachable
```

Then try the lifecycle commands (`lab.ps1 <cmd>` / `lab.sh <cmd>`):

| Command | Shows |
|---|---|
| `revoke reporting` | **revocation**: certificate on the CRL → sidecars reload → reporting is refused at the TLS layer |
| `reissue reporting` | a fresh certificate (new serial) is accepted again; only the old one is revoked |
| `rotate` | **rotation**: every service gets a new key and certificate, sidecars reload, **zero app changes**. The admin cert hash changes |
| `test` | run the scenarios again |
| `down` | stop (certificates stay in `pki/out/`) |

## What's in here

| Path | What |
|---|---|
| `users-service/`, `orders-service/` | FastAPI apps. Same layout as the other labs (`app/main.py`, `dependencies.py`, `routers/`, `tests/`). They listen on **127.0.0.1 only** and read the caller from the sidecar's `x-forwarded-client-cert` header |
| `envoy/users.yaml`, `envoy/orders.yaml` | Sidecar configs: inbound mTLS (CA + CRL + SPIFFE prefix), identity forwarding (SANITIZE_SET), and egress mTLS from orders to users with **server identity pinned** to `spiffe://lab.local/users` |
| `pki/pki.sh` | The lab CA: `init`, `issue <name> [hours]` (24 h by default), `ensure`, `revoke`, `foreign`, `show`. Runs in a container, so the host needs no openssl |
| `client/call.py` | Call any service as any identity: `docker compose run --rm client call.py --as reporting GET https://orders-app:8443/orders/` |
| `client/scenarios.py` | The lessons above as checks |
| `scripts/lab.ps1`, `scripts/lab.sh` | setup / test / revoke / reissue / rotate / down |

## Who may call what

| | admin | reporting | orders (service) | anyone with a valid cert |
|---|---|---|---|---|
| users `GET` | ✅ | ✅ | ✅ | 403 |
| users `POST` | ✅ | 403 | 403 | 403 |
| orders `POST` (calls users) | ✅ | 403 | 403 | 403 |
| orders `GET` | ✅ | ✅ | 403 | 403 |
| `/whoami` (both) | ✅ | ✅ | ✅ | ✅ |
| **no cert / foreign CA / revoked cert** | refused at the TLS handshake, before any HTTP | | | |

## Try it by hand

From the client container (works the same on Windows and macOS):
```bash
docker compose run --rm client call.py --as admin GET https://orders-app:8443/whoami
docker compose run --rm client call.py --as admin POST https://users-app:8443/users/ '{"username":"dave","email":"dave@example.com"}'
docker compose run --rm client call.py --as reporting POST https://orders-app:8443/orders/ '{"user_id":1,"item":"tea"}'   # 403
docker compose run --rm client call.py --no-cert GET https://orders-app:8443/whoami                                         # refused
docker compose run --rm client call.py --foreign GET https://orders-app:8443/whoami                                         # refused
```
From the host on **macOS / Linux** (the sidecars are published on 8443 = orders, 8444 = users):
```bash
curl --cert pki/out/admin.crt --key pki/out/admin.key --cacert pki/out/ca.crt https://localhost:8443/whoami
```
(Windows' built-in curl uses Schannel, which can't load these PEM keys, so use the client container there.)

Envoy stats (TLS handshakes, verification failures): http://127.0.0.1:9901/stats?filter=ssl

## Compared with the other auth labs

| | keykloak-python, keycloak-jwt-python, oauth2-bff-python | **mtls-services-python** |
|---|---|---|
| Who authenticates | **people** (browser, Keycloak) | **services / workloads** (no people, no browser) |
| Credential | password, Kerberos ticket, or session cookie → JWT | **X.509 certificate + private key**, checked in the TLS handshake |
| Where it's checked | Keycloak + the API (JWT or session) | the **sidecar**; the app only reads a trusted header |
| In the industry | SSO / OIDC for users | **zero-trust service mesh** (Istio, Linkerd, SPIFFE/SPIRE), partner APIs with mTLS |

> Lab-only: 24 h certificates issued by a script (production: minutes to hours, issued automatically by the mesh), the CA key on disk, keys readable by the sidecar user, in-memory data. See [docs/production.md](docs/production.md).
