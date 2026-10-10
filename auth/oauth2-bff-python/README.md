# OAuth 2.0 BFF lab (backend-for-frontend)

The same small website as the other labs (users and profiles, full CRUD), secured with **OAuth 2.0 the BFF way**:
- **The FastAPI backend is the OAuth 2.0 client.** It runs the authorization-code flow with Keycloak (client secret + PKCE) and verifies the ID token.
- It keeps a **server-side session** and gives the browser only an **HttpOnly cookie**. **No token ever reaches JavaScript.**
- Guests can browse; signing in unlocks create, edit and delete. **Sign in → Log in / Register** use Keycloak's pages.

```
Browser ──► http://localhost:5175 (one origin: SPA + Vite proxy for /api and /auth)
              │  /auth/login ──► FastAPI ──302──► Keycloak login page (:8082)
              │  /auth/callback ◄── Keycloak ── FastAPI swaps the code for tokens (back-channel),
              │                                 verifies the ID token, stores a session → Set-Cookie: bff_session (HttpOnly)
              └─ /api/* with the cookie (+ X-CSRF header on writes) ──► FastAPI ──► session row in Postgres
```

**New here? Start with [GETTING-STARTED.md](GETTING-STARTED.md)** (step by step, with a check after each step).

## The auth labs side by side

| | `keykloak-python` | `keycloak-jwt-python` | **`oauth2-bff-python` (this)** |
|---|---|---|---|
| Users prove who they are with | Kerberos ticket or password | password on Keycloak's page | password on Keycloak's page |
| OAuth client | the SPA (public) | the SPA (public) | **the backend (confidential: secret + PKCE)** |
| Browser holds | a JWT in JS memory | a JWT in JS memory | **only an HttpOnly cookie** |
| API checks | JWT signature (JWKS) per request | JWT signature (JWKS) per request | **session row** per request (token verified once, at login) |
| CSRF protection | not needed | not needed | **SameSite=Lax + `X-CSRF: 1` header** on writes |
| CORS | needed | needed | **none** (same origin) |
| Logout effective | when the token expires (~5 min) | when the token expires | **immediately** (session row deleted + Keycloak back-channel logout) |
| Keycloak / realm | `keycloak.lab.local:8080` / `lab` | `localhost:8081` / `jwt-lab` | **`localhost:8082` / `bff-lab`** |
| API / site / Postgres | 8000 / 5173 / 5434 | 8001 / 5174 / 5435 | **8002 / 5175 / 5436** |

All three can run at the same time.

## What's in here

| Folder / file | What it is |
|---|---|
| `docker-compose.yml` | Postgres (`db`) and Keycloak |
| `keycloak/bff-lab-realm.json` | The realm: **confidential client `bff`** (lab secret `bff-lab-client-secret`, PKCE, redirect URI `http://localhost:5175/auth/callback`), registration, login by username or email, demo user **`alice` / `alice123`** |
| `postgres/` | `create-databases.sql`: roles and databases `app` + `keycloak` |
| `fastapi-seerver/` | API + OAuth client: `/auth/login`, `/auth/register`, `/auth/callback`, `/auth/logout`; `/api/users`, `/api/profiles` (reads public, writes need the cookie + `X-CSRF`), `/api/me`. Design docs in [fastapi-seerver/docs/](fastapi-seerver/docs/) |
| `frontend/` | React + TypeScript (Vite). **No OAuth library**: `auth/session.ts` asks `/api/me`, `auth/apiFetch.ts` adds `X-CSRF` on writes, and the Sign in menu just navigates to `/auth/*`. `vite.config.ts` proxies `/api` and `/auth` |

> Lab only: plain HTTP (`Secure` cookies off), the client secret in the realm JSON, a seeded demo user, `admin/admin`. Don't reuse these settings anywhere real.

## Quick setup (one command, no admin rights)

Start Docker Desktop, then:
```powershell
cd fastapi-seerver
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```
It starts Postgres and Keycloak, builds the backend (`alembic upgrade head` creates `users`, `profiles` and `sessions`), installs the frontend, then runs FastAPI (:8002) and Vite (:5175) in the same terminal (Ctrl+C stops both) and opens http://localhost:5175. Safe to re-run.

### macOS / Linux

Same steps with the bash version (no sudo needed: this lab has no Kerberos):
```bash
cd fastapi-seerver
bash scripts/setup-local-dev.sh            # or: --no-start
```
It opens http://localhost:5175 in your default browser. Manual commands are the same as on Windows, with `.venv/bin/` instead of `.venv\Scripts\` (see [GETTING-STARTED.md](GETTING-STARTED.md)).

> **Status on macOS:** written for macOS (bash 3.2, the version Apple ships). Its logic was tested in Linux containers under bash 3.2: start and Ctrl+C cleanup, and the parts every OS shares (Docker, Python, npm). It hasn't been run on a real Mac yet. If a step fails there, the message says which one.

## Use the site

1. http://localhost:5175: you're a **guest** (lists visible, no edit buttons).
2. **Sign in → Log in** with `alice` / `alice123` (or `alice@example.com`). The browser goes to Keycloak, back to `/auth/callback`, then home, signed in.
3. Open the browser dev tools → Application → Cookies: you'll see **`bff_session` (HttpOnly)** and no token anywhere (not in Local Storage, not in responses).
4. Create, edit and delete users and profiles. **Log out** ends the app session and Keycloak's session, so the next login asks for the password again.
5. **Sign in → Register** creates a Keycloak account and signs you in.

## Two kinds of "user", plus sessions

| | Created by | Lives in |
|---|---|---|
| **Account** (alice, registered users) | realm import / Sign in → Register | Postgres database `keycloak` |
| **Session** (a signed-in browser) | `/auth/callback` after a verified login | Postgres `app.sessions` (only a hash of the cookie, plus `sub`, username, email, expiry) |
| **App user / profile** (the CRUD data) | any signed-in person | Postgres `app.users`, `app.profiles` |

> Any signed-in account can edit or delete **any** record; there are no owners or roles yet ([architecture gaps](fastapi-seerver/docs/architecture.md#6-known-gaps-and-risks)).

## Database

Same setup as the other labs: one Postgres, databases `app` and `keycloak`, each with its own role; a Docker container on **5436** by default, or an installed Postgres / AWS RDS via `.env` (`COMPOSE_PROFILES`, `KC_DB_URL`) and `fastapi-seerver/.env` (`DATABASE_URL`). See "Database" in `../keykloak-python/README.md` for the three modes.

```bash
docker compose exec db psql -U app -d app -c "select left(id,12) as id_hash, username, expires_at from sessions"
docker compose down -v && docker compose up -d && (cd fastapi-seerver && alembic upgrade head)   # start fresh
```

## Tests

```bash
cd fastapi-seerver && pytest    # 10 tests: cookie/CSRF/expiry/logout, the full callback (Keycloak mocked), open-redirect guard, CRUD
cd frontend && npm test         # Sign in menu (navigation, logout with X-CSRF), UserForm
cd frontend && npm run build    # strict TypeScript
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| Keycloak: "Invalid parameter: redirect_uri" | the site isn't on http://localhost:5175, or `APP_URL` in `fastapi-seerver/.env` doesn't match the redirect URI of client `bff` |
| `/auth/callback` → 400 "Invalid or expired login" | the login took over 10 min, cookies are blocked, or the callback opened in a different browser. Start again from Sign in |
| `/auth/callback` → 400 "Code exchange with Keycloak failed" | `OIDC_CLIENT_SECRET` in `fastapi-seerver/.env` ≠ the client's secret in Keycloak |
| Writes → 403 "Missing X-CSRF header" | expected for tools like curl: add `-H "X-CSRF: 1"`. The site adds it automatically |
| Page shows "Could not reach the backend at /api" | FastAPI isn't running on :8002, or you opened FastAPI's port instead of the site's 5175 |
| Writes from FastAPI's Swagger UI (http://localhost:8002/docs) → 403 | the session cookie does reach :8002 (browsers don't separate cookies by port), but Swagger doesn't send `X-CSRF`. Use the site for writes; reads work in Swagger |
| Edits to `bff-lab-realm.json` don't apply | imported only on first start: `docker compose down -v` |
