# fastapi-seerver

FastAPI service for the mTLS lab. Writes require a verified **client certificate**; reads are public. TLS and
the client-cert check happen in **nginx** in front of this service, which forwards the result as the headers
`X-SSL-Client-Verify` and `X-SSL-Client-DN`. The full lab is in [../README.md](../README.md).

This service is **not published to the host** — it is reachable only through nginx on the Docker network, which
is what makes those headers trustworthy (see [docs/architecture.md §5](docs/architecture.md)).

Design docs:
- [docs/architecture.md](docs/architecture.md): the proxy pattern, the trust boundary, decisions, gaps
- [docs/datamodel.md](docs/datamodel.md): `users`/`profiles` (the credential is the cert, not a table)
- [docs/dataflow.md](docs/dataflow.md): read vs. write, the 401 paths, why headers can't be forged
- [docs/deployment.md](docs/deployment.md): managed CA, revocation, ingress/mesh equivalents

## Run

From the lab root: `docker compose up --build` (after `certs/make-certs.*`). This container runs
`alembic upgrade head` then `uvicorn app.main:app`.

## Test (host, no Docker)

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt   # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m pytest        # cert-header checks + CRUD on in-memory SQLite
```
