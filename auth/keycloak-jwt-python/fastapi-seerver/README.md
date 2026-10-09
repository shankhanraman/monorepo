# fastapi-seerver

FastAPI service that trusts Keycloak-issued JWTs (users log in or register on Keycloak's pages with a password; no Kerberos).
The full lab is explained in [../README.md](../README.md).

Design docs:
- [docs/architecture.md](docs/architecture.md): components, trust boundaries, key decisions, known gaps
- [docs/datamodel.md](docs/datamodel.md): entities, tables and constraints, identity claims, migrations workflow
- [docs/dataflow.md](docs/dataflow.md): login, request pipeline, refresh, key rotation, error reference
- [docs/deployment.md](docs/deployment.md): production target: GitHub Actions CI/CD, secrets management, Kubernetes (not built yet)

## Setup (Windows)

Start Docker Desktop, then (no admin rights needed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

This sets up Postgres, Keycloak (realm `jwt-lab`), this backend's `.venv` and tables, and the frontend, then starts everything (API on :8001, site on :5174). It's safe to re-run.

Data is stored in PostgreSQL database `app` (`DATABASE_URL` in `.env`; a Docker container by default, or an installed server or AWS RDS; see "Database" in [../README.md](../README.md)).

## Run / test manually

```powershell
.venv\Scripts\activate
alembic upgrade head        # create/upgrade the tables in DATABASE_URL
fastapi dev app/main.py --port 8001   # http://localhost:8001/docs
pytest                      # auth + CRUD tests on in-memory SQLite: no Keycloak or Postgres needed
```
