# Auth labs: start here

This folder contains separate, runnable examples of common authentication methods. They all protect a small FastAPI CRUD app. Start with **JWT** for the normal browser login flow; start with **API key** for the fastest demo.

## Choose a lab

| Lab | Best for | Start URL | Main idea |
|---|---|---:|---|
| `api-key-python` | Fastest demo, scripts, machine-to-machine calls | `http://localhost:5177` | Send `X-API-Key` on protected requests |
| `keycloak-jwt-python` | Standard SPA login | `http://localhost:5174` | React gets a JWT and sends `Authorization: Bearer ...` |
| `oauth2-bff-python` | Recommended production-style browser pattern | `http://localhost:5175` | Backend handles OAuth; browser receives only an HttpOnly session cookie |
| `saml-python` | Enterprise SSO / SAML | `http://localhost:8006/saml/login` | Keycloak IdP sends a signed SAML assertion to FastAPI |
| `mtls-python` | Service-to-service or certificate identity | `https://localhost:8443` | nginx verifies a client certificate before forwarding |
| `keykloak-python` | Kerberos / passwordless corporate login | `http://localhost:5173` | Browser uses a Kerberos ticket through Keycloak |

All examples are labs only: they use local HTTP, demo passwords/keys, and development secrets. Do not copy those credentials or settings into production.

## Fastest start: API key lab

Prerequisite: Docker Desktop must be running.

From PowerShell:

```powershell
cd C:\Users\workf\OneDrive\Desktop\monorepo\auth\api-key-python\fastapi-seerver
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

The script starts PostgreSQL, creates the Python environment and tables, seeds demo keys, starts FastAPI and Vite, and opens the app. If it finishes without starting the processes, use two terminals:

```powershell
# terminal 1
cd C:\Users\workf\OneDrive\Desktop\monorepo\auth\api-key-python\fastapi-seerver
.venv\Scripts\fastapi.exe dev app\main.py --port 8004

# terminal 2
cd C:\Users\workf\OneDrive\Desktop\monorepo\auth\api-key-python\frontend
npm install
npm run dev
```

Open `http://localhost:5177`.

- Read requests are public.
- Paste `mial_live_demo_do_not_use_in_prod` into **Use API key** to enable writes.
- `mial_live_revoked_example` must return `401`.
- API docs: `http://localhost:8004/docs`.

Quick API check:

```powershell
Invoke-RestMethod http://localhost:8004/users/
Invoke-RestMethod http://localhost:8004/me -Headers @{ "X-API-Key" = "mial_live_demo_do_not_use_in_prod" }
```

## Recommended browser auth: JWT

This is the easiest lab for understanding a conventional SPA plus identity provider setup.

```powershell
cd C:\Users\workf\OneDrive\Desktop\monorepo\auth\keycloak-jwt-python\fastapi-seerver
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

Open `http://localhost:5174` and log in with `alice` / `alice123`.

```text
Browser -> React :5174 -> Keycloak :8081
                         <- authorization code + PKCE
React -> FastAPI :8001 with Authorization: Bearer <JWT>
FastAPI -> verifies JWT signature, issuer, audience, and expiry
```

Important files to read in order:

1. `keycloak-jwt-python/frontend/src/auth/` — login and token usage.
2. `keycloak-jwt-python/fastapi-seerver/app/dependencies.py` — token verification.
3. `keycloak-jwt-python/fastapi-seerver/app/routers/users.py` — public versus protected routes.
4. `keycloak-jwt-python/keycloak/jwt-lab-realm.json` — client, realm, audience, and demo user configuration.

## Recommended production-style browser auth: OAuth 2.0 BFF

Use this when you want the browser to avoid holding access or ID tokens.

```powershell
cd C:\Users\workf\OneDrive\Desktop\monorepo\auth\oauth2-bff-python\fastapi-seerver
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

Open `http://localhost:5175` and log in with `alice` / `alice123`.

```text
Browser -> FastAPI /auth/login -> Keycloak :8082
Browser <- one-time callback code
FastAPI -> exchanges code server-to-server using client secret
FastAPI -> creates session in PostgreSQL
Browser <- HttpOnly bff_session cookie
Browser -> API with cookie + X-CSRF on writes
```

The browser should see a session cookie, not a token. Read `oauth2-bff-python/fastapi-seerver/app/routers/auth.py` first, then `app/dependencies.py` and `frontend/src/`.

## How protected requests work

Every lab follows the same high-level rule:

```text
credential arrives -> server validates it -> request gets an identity -> protected route allows/denies
```

The credential differs:

- API key: hash the `X-API-Key`, find an active database row, then allow.
- JWT: verify the signature using Keycloak JWKS, then check `iss`, `aud`, and `exp`.
- OAuth BFF: look up the random session cookie in the database; require CSRF protection for writes.
- SAML: validate the signed assertion at the ACS endpoint, then issue a session cookie.
- mTLS: nginx verifies the client certificate and forwards the verified identity to FastAPI; FastAPI is not publicly exposed.
- Kerberos: Keycloak validates the browser's SPNEGO ticket and then issues a JWT; FastAPI only understands the JWT.

In all labs, public `GET` routes demonstrate anonymous access, while create/update/delete routes normally return `401` without valid authentication. A successful login is not authorization: these demos mostly prove identity and do not implement per-user ownership or roles.

## Run tests

Run tests from the lab's backend directory:

```powershell
.venv\Scripts\python.exe -m pytest
```

For labs with a React frontend:

```powershell
npm test
npm run build
```

The repository's tested status is summarized in [`LIVE-TEST-RESULTS.md`](LIVE-TEST-RESULTS.md).

## Stop or reset

Press `Ctrl+C` for locally running FastAPI/Vite processes. In the lab directory:

```powershell
docker compose down       # stop and remove containers; keep volume data
docker compose down -v    # wipe accounts and app data; use only for a clean reset
```

Common fixes:

- Docker errors: start Docker Desktop and wait for `docker info` to work.
- `relation does not exist`: run `alembic upgrade head` in that lab's `fastapi-seerver` directory.
- Redirect URI errors: use the exact frontend port documented for that lab.
- Keycloak not ready: wait 30–60 seconds, then inspect `docker compose logs keycloak`.
- `401` after changing labs: log out and make sure the token/session came from the same lab and port.

## Deeper guides

- [JWT step-by-step](keycloak-jwt-python/GETTING-STARTED.md)
- [OAuth BFF step-by-step](oauth2-bff-python/GETTING-STARTED.md)
- [API key step-by-step](api-key-python/GETTING-STARTED.md)
- [SAML step-by-step](saml-python/GETTING-STARTED.md)
- [mTLS step-by-step](mtls-python/GETTING-STARTED.md)
- [Live verification results](LIVE-TEST-RESULTS.md)
