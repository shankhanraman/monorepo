# fastapi-seerver

FastAPI service that trusts Keycloak-issued JWTs (Keycloak logs users in with Kerberos).
The full lab is explained in [../README.md](../README.md).

Design docs:
- [docs/architecture.md](docs/architecture.md): components, trust boundaries, key decisions, known gaps
- [docs/datamodel.md](docs/datamodel.md): entities, tables and constraints, identity claims, migrations workflow
- [docs/dataflow.md](docs/dataflow.md): login, request pipeline, refresh, key rotation, error reference

## Setup (Windows)

Start Docker Desktop, then:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

This sets up Postgres, Kerberos, Keycloak, this backend's `.venv` and tables, and the frontend, gets you a Kerberos ticket, and starts everything. It's safe to re-run.

Data is stored in PostgreSQL database `app` (`DATABASE_URL` in `.env`; a Docker container by default, or an installed server or AWS RDS; see "Database" in [../README.md](../README.md)).

## Run / test manually

```powershell
.venv\Scripts\activate
alembic upgrade head        # create/upgrade the tables in DATABASE_URL
fastapi dev app/main.py     # http://localhost:8000/docs
pytest                      # auth + CRUD tests on in-memory SQLite: no Keycloak or Postgres needed
```
