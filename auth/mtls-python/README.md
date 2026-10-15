# mTLS (client certificate) lab

The same users-and-profiles API as the other labs, secured with **mutual TLS**: the client proves who it is
with a **certificate** presented during the TLS handshake. Reads are public; writes require a client cert that
our CA signed.

Unlike the other labs there is no login page and no token — identity is the **client certificate** itself. The
natural client is a service or `curl` (not a browser), so this lab is driven from the command line.

```
curl --cert client.crt --key client.key  -->  nginx :8443  (verifies the cert against our CA)
                                               |  sets X-SSL-Client-Verify / X-SSL-Client-DN
                                               v
                                          FastAPI (internal)  --> writes allowed only when Verify = SUCCESS
```

## Why nginx is in front (the key idea)

A plain ASGI server (uvicorn) can't hand the client certificate to the app. So **nginx terminates TLS,
verifies the client cert against our CA, and forwards the result as headers**:

| Header | Value |
|---|---|
| `X-SSL-Client-Verify` | `SUCCESS` / `FAILED:<reason>` / `NONE` |
| `X-SSL-Client-DN` | the client cert subject, e.g. `CN=alice` |

**FastAPI trusts those headers only because it is unreachable except through nginx** — the `server` container
publishes no host port (see `docker-compose.yml`). If a client could reach FastAPI directly, it could just send
`X-SSL-Client-Verify: SUCCESS` and bypass mTLS. That trust boundary *is* the lesson of this lab.

## The teachable files

| File | What it shows |
|---|---|
| [`certs/make-certs.sh`](certs/make-certs.sh) | a self-signed CA, a server cert (CN=localhost), a client cert (CN=alice) |
| [`nginx/nginx.conf`](nginx/nginx.conf) | `ssl_verify_client optional` + forwarding the verify result (`proxy_set_header` can't be spoofed) |
| [`fastapi-seerver/app/dependencies.py`](fastapi-seerver/app/dependencies.py) | `current_cert`: the whole check — require `X-SSL-Client-Verify == SUCCESS` |
| [`docker-compose.yml`](docker-compose.yml) | the trust boundary: `server` is internal-only; `nginx` is the one published port |

## Ports

| | this lab |
|---|---|
| nginx (mTLS entry) | 8443 (HTTPS) |
| FastAPI | internal only (not published) |
| Postgres | 5439 |

## Setup

Needs Docker Desktop and `openssl`.

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File fastapi-seerver\scripts\setup-local-dev.ps1
```
```bash
# macOS / Linux / Git Bash
bash fastapi-seerver/scripts/setup-local-dev.sh
```

It generates the certs (`certs/`), copies `.env`, and runs `docker compose up --build` (db + server + nginx).
Or by hand:

```bash
bash certs/make-certs.sh          # CA + server + client certs into certs/
cp .env.example .env
docker compose up --build -d      # db + server (internal) + nginx (:8443)
```

## Try it (curl)

From `certs/` (so the cert files are local). **macOS / Linux:**

```bash
curl --cacert ca.crt https://localhost:8443/users/                                   # 200  public read, no cert
curl --cacert ca.crt -X POST https://localhost:8443/users/ \
     -H 'Content-Type: application/json' -d '{"username":"a","email":"a@example.com"}'   # 401  write, no client cert
curl --cacert ca.crt --cert client.crt --key client.key -X POST https://localhost:8443/users/ \
     -H 'Content-Type: application/json' -d '{"username":"a","email":"a@example.com"}'   # 201  write, with client cert
curl --cacert ca.crt --cert client.crt --key client.key https://localhost:8443/me        # {"cn":"alice"}
```

**Windows** curl uses Schannel: add `--ssl-no-revoke` (the self-signed CA has no revocation list). Presenting a
PEM client cert via Schannel is unreliable; use one of:
- import `certs/client.p12` (password `changeit`) into the Windows cert store, then `curl --cert`, or
- run curl from **WSL**, or
- run it from a Linux container on the lab network:
  ```bash
  docker run --rm --network mtls-python_lab -v "$PWD/certs:/certs:ro" curlimages/curl \
    --connect-to localhost:8443:nginx:8443 \
    --cacert /certs/ca.crt --cert /certs/client.crt --key /certs/client.key https://localhost:8443/me
  ```

## Browser (optional)

A browser can do mTLS too, but it's fiddly: import `certs/client.p12` into the browser/OS, then visit
`https://localhost:8443/users/` and accept the self-signed server cert. That's why this lab leads with curl and
ships no SPA.

## Confirm the trust boundary

```bash
docker compose ps            # 'server' shows no published port; only nginx maps 8443
curl -m3 http://localhost:8000/users/   # fails to connect: FastAPI isn't reachable, so its headers can't be forged
```

## Tests

```bash
cd fastapi-seerver
uv venv --python 3.12 .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python -m pytest        # cert-header checks (SUCCESS/NONE/FAILED) + CRUD, on SQLite, no Docker
```

## Security notes

- The client cert is verified **against our CA** — any cert the CA signed is trusted. Scope by CN/SAN for finer control.
- **Plain self-signed, no CRL/OCSP** — lab only. Real mTLS needs a managed CA and revocation.
- The app trusts `X-SSL-*` only because FastAPI is unreachable except via nginx. In production enforce that with
  network policy (and/or a shared secret between proxy and app).
- Certs live in `certs/` and are **gitignored** — regenerate with `make-certs`, never commit keys.
