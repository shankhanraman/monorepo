# fastapi-seerver

FastAPI service where writes require an **API key** in the `X-API-Key` header; reads are public. No Keycloak.
The full lab is explained in [../README.md](../README.md).

Design docs:
- [docs/architecture.md](docs/architecture.md): components, the auth check, decisions, known gaps
- [docs/datamodel.md](docs/datamodel.md): `users`, `profiles`, and the `api_keys` table (hash + prefix + active)
- [docs/dataflow.md](docs/dataflow.md): public read, write-with-key, the 401 paths, `/me`
- [docs/deployment.md](docs/deployment.md): what to change before real use (HTTPS, minting, rate-limit)

## Setup (Windows)

Start Docker Desktop, then (no admin rights needed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

This sets up Postgres, this backend's `.venv` and tables (seeding two demo keys), and the frontend, then starts
everything (API on :8004, site on :5177). It's safe to re-run.

## Run / test manually

```powershell
alembic upgrade head                      # create tables + seed demo keys in DATABASE_URL
.venv\Scripts\fastapi.exe dev app/main.py --port 8004   # http://localhost:8004/docs
.venv\Scripts\python.exe -m pytest        # auth + CRUD on in-memory SQLite: no Postgres needed
```

Seeded demo keys: `mial_live_demo_do_not_use_in_prod` (active), `mial_live_revoked_example` (revoked).
