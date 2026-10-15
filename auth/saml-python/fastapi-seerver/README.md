# fastapi-seerver

FastAPI **SAML 2.0 Service Provider** using `python3-saml`. Keycloak is the IdP. Writes require a session the SP
issues after it verifies a signed SAML assertion; reads are public. The full lab is in [../README.md](../README.md).

Runs in Docker (the `Dockerfile` apt-installs `libxmlsec1` for XML signature verification). `onelogin`/`xmlsec`
are imported lazily so the host test suite can import the app without the native library.

Design docs:
- [docs/architecture.md](docs/architecture.md): the SP/IdP split, the SAML flow, the Destination gotcha, decisions
- [docs/datamodel.md](docs/datamodel.md): `users`/`profiles` (identity is the signed assertion, not a table)
- [docs/dataflow.md](docs/dataflow.md): SSO step by step, the 401/400 paths, why the assertion is trusted
- [docs/deployment.md](docs/deployment.md): HTTPS, SLO, request signing, IdP-agnostic pattern

## Run

From the lab root: `docker compose up --build` → db + keycloak + this SP. It runs `alembic upgrade head` then
`uvicorn app.main:app`.

## Test (in the container — the host has no xmlsec)

```bash
docker compose run --rm server python -m pytest -q
```

Covers the session-cookie gate and CRUD. The signature verification is exercised by `../../saml_login_test.py`.

## Endpoints

`GET /saml/login` · `POST /saml/acs` · `GET /saml/metadata` · `GET /me` · `GET/POST/PUT/DELETE /users` + `/profiles`.
