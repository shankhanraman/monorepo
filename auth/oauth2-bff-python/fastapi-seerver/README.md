# fastapi-seerver

FastAPI service that is both the **business API** and the **OAuth 2.0 client** (backend-for-frontend):
- it runs the authorization-code flow with Keycloak (client secret + PKCE) and verifies the ID token;
- it keeps a server-side session in Postgres and gives the browser only an HttpOnly cookie. No token reaches the browser.

The full lab is explained in [../README.md](../README.md), and step by step in [../GETTING-STARTED.md](../GETTING-STARTED.md).

Design docs:
- [docs/architecture.md](docs/architecture.md): BFF vs SPA tokens, components, auth checks, CSRF, decisions, known gaps
- [docs/datamodel.md](docs/datamodel.md): users, profiles, **sessions** (hashed cookie ids), ID-token claims, migrations
- [docs/dataflow.md](docs/dataflow.md): login / callback / logout sequences, cookie + CSRF request pipeline, error reference
- [docs/deployment.md](docs/deployment.md): production target: one ingress host, secrets, Kubernetes (not built yet)

| Path | What |
|---|---|
| `GET /auth/login`, `GET /auth/register` | start the OAuth flow (redirect to Keycloak's login or sign-up page) |
| `GET /auth/callback` | Keycloak returns here: code → tokens (back-channel), ID token checked, session cookie set |
| `POST /auth/logout` | needs `X-CSRF: 1`; deletes the session, ends the Keycloak session server-to-server |
| `GET /api/me` | the signed-in user, or 401 |
| `/api/users`, `/api/profiles` | CRUD: reads public, writes need the session cookie **and** `X-CSRF: 1` |
| `GET /health` | liveness |

## Setup (Windows)

Start Docker Desktop, then (no admin rights needed):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

This sets up Postgres, Keycloak (realm `bff-lab`), this backend's `.venv` and tables, and the frontend, then starts everything (API on :8002, site on :5175). It's safe to re-run.

## Run / test manually

```powershell
.venv\Scripts\activate
alembic upgrade head                    # users, profiles (0001) + sessions (0002)
fastapi dev app/main.py --port 8002     # http://localhost:8002/docs
pytest                                  # 10 tests: auth (Keycloak mocked) + CRUD on in-memory SQLite, no Docker needed
```

Open the **site** (http://localhost:5175), not this port, to sign in: the redirect URI and the cookie belong to the site's origin.
