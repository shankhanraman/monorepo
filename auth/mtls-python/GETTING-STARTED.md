# Getting started, step by step

Bring up the mTLS lab piece by piece. Everything runs in Docker; `curl` drives it.
Prerequisites: Docker Desktop (running) and `openssl`.

What you'll end up with:

| Piece | Address | Runs in |
|---|---|---|
| nginx (mTLS entry) | https://localhost:8443 | Docker |
| FastAPI | internal only (not published) | Docker |
| PostgreSQL | localhost:5439 | Docker |

## Step 1: Generate the certificates

```bash
bash certs/make-certs.sh          # Windows: powershell -ExecutionPolicy Bypass -File certs\make-certs.ps1
```

Creates in `certs/`: `ca.crt`/`ca.key` (the CA), `server.crt`/`server.key` (for nginx, CN=localhost),
`client.crt`/`client.key` (CN=alice) and `client.p12` (for a browser). Check:

```bash
openssl verify -CAfile certs/ca.crt certs/client.crt     # certs/client.crt: OK
```

## Step 2: Start everything

```bash
cp .env.example .env              # first time
docker compose up --build -d      # db + server (FastAPI) + nginx
docker compose ps                 # 'server' has NO published port; nginx maps 8443
```

The `server` service runs `alembic upgrade head` then uvicorn, both inside the container.

## Step 3: Use it (curl from certs/)

```bash
cd certs
curl --cacert ca.crt https://localhost:8443/health                                   # {"status":"ok"}
curl --cacert ca.crt https://localhost:8443/users/                                   # 200, public read (no cert)
curl --cacert ca.crt -X POST https://localhost:8443/users/ \
     -H 'Content-Type: application/json' -d '{"username":"a","email":"a@example.com"}'   # 401, no client cert
curl --cacert ca.crt --cert client.crt --key client.key -X POST https://localhost:8443/users/ \
     -H 'Content-Type: application/json' -d '{"username":"a","email":"a@example.com"}'   # 201, with client cert
curl --cacert ca.crt --cert client.crt --key client.key https://localhost:8443/me        # {"cn":"alice"}
```

> **Windows:** add `--ssl-no-revoke`. Client-cert writes via Schannel are unreliable — use WSL, import
> `client.p12` into the Windows store, or a Linux curl container (see [README.md](README.md)).

## Step 4: See the trust boundary

```bash
curl -m3 http://localhost:8000/users/     # connection fails: FastAPI isn't exposed, so its X-SSL-* headers can't be forged
```

## Step 5 (optional): Tests

```bash
cd fastapi-seerver
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m pytest
```

## Stopping / fresh start

| What | Command |
|---|---|
| Stop | `docker compose down` |
| Wipe data | `docker compose down -v` |
| New certs | re-run `make-certs`, then `docker compose restart nginx` |

## If a step fails

| Problem | Fix |
|---|---|
| `make-certs` openssl error about a `.cnf` path | the script sets its own config; make sure you ran it from the repo (it `cd`s to `certs/`) |
| curl exit 60 on Windows | Schannel can't check revocation for the self-signed CA → add `--ssl-no-revoke` |
| curl exit 35 presenting a client cert on Windows | Schannel limitation → use WSL / the Linux curl container / import the `.p12` |
| write returns 401 with the client cert | is nginx using the same CA that signed the cert? re-run `make-certs` and `docker compose up -d` |
| `000` to https://localhost:8443 | nginx not up yet: `docker compose ps`, `docker compose logs nginx` |
