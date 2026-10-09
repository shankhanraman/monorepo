# Getting started, step by step

How to start the OAuth 2.0 BFF lab **by hand, one piece at a time**, on Windows (PowerShell), with a check after each step.
In a hurry? `fastapi-seerver\scripts\setup-local-dev.ps1` does steps 2–8 in one go (see [README.md](README.md)).

What you'll end up with:

| Piece | Address | Runs in |
|---|---|---|
| PostgreSQL | `localhost:5436` | Docker |
| Keycloak (login server) | http://localhost:8082 | Docker |
| FastAPI (backend + OAuth client) | http://localhost:8002 | terminal 1 |
| React site + proxy for `/api`, `/auth` | **http://localhost:5175** (the only address you open) | terminal 2 |

---

## Step 0: Check the tools (once)

```powershell
docker --version          # Docker Desktop must be installed AND running (whale icon in the tray)
docker info               # errors here = Docker Desktop isn't started yet
uv --version              # or: py -3.12 --version   (Python 3.12 for the backend)
node --version            # 22 or newer (20.19+ also works)
```

**Why:** Postgres and Keycloak run in Docker, the backend needs Python 3.12, and the frontend needs Node.

---

## Step 1: Go to the project folder

```powershell
cd C:\monorepo\auth\oauth2-bff-python
```

All commands below start from this folder unless a step says `cd` somewhere else.

---

## Step 2: Create the settings files (once)

```powershell
Copy-Item .env.example .env
Copy-Item fastapi-seerver\.env.example fastapi-seerver\.env
```

**Why:** `.env` holds the passwords and addresses (database, Keycloak, and in `fastapi-seerver\.env` the OAuth **client secret** and `SESSION_SECRET`). The `.example` files are templates that are committed to git. The real `.env` files are not (they're in `.gitignore`).

**Check:** `Get-Content .env` shows `COMPOSE_PROFILES=local-db` and the database passwords.

---

## Step 3: Start the database

```powershell
docker compose up -d db
```

**Why:** Postgres stores everything: the site's users, profiles and login **sessions** (database `app`) and Keycloak's accounts (database `keycloak`). On the **first** start it runs `postgres/create-databases.sql`, which creates both databases and their roles.

**Check:** wait until the status says **(healthy)**:
```powershell
docker compose ps db
```

---

## Step 4: Start Keycloak

```powershell
docker compose up -d keycloak
```

**Why:** Keycloak shows the login and sign-up pages and issues tokens **to the backend** (never to the browser). On its **first** start it imports `keycloak/bff-lab-realm.json`: the realm `bff-lab`, the confidential client `bff` (with its secret), and the demo user `alice`.

**Check:** the first start takes about 30–60 s. Repeat this until it prints the issuer:
```powershell
(Invoke-RestMethod http://localhost:8082/realms/bff-lab/.well-known/openid-configuration).issuer
# expected: http://localhost:8082/realms/bff-lab
```
If it fails, look at the log: `docker compose logs keycloak`

Optional: admin console at http://localhost:8082, `admin` / `admin`, then switch to realm **bff-lab** → Clients → `bff` (Credentials tab shows the client secret).

---

## Step 5: Backend: Python environment (once)

```powershell
cd fastapi-seerver
uv venv --python 3.12 .venv                                        # or: py -3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt   # or: .venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Why:** a separate Python environment (`.venv`) for this project, with FastAPI, PyJWT (to verify the ID token), httpx (to talk to Keycloak), SQLAlchemy, Alembic, etc.

**Check:**
```powershell
.venv\Scripts\python.exe -c "import fastapi, jwt, httpx, sqlalchemy; print('ok')"
```

> The commands below call `.venv\Scripts\...` directly, so you don't need to "activate" the environment. (If you prefer to activate it and PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` first.)

---

## Step 6: Create the tables

Still in `fastapi-seerver`:
```powershell
.venv\Scripts\alembic.exe upgrade head
```

**Why:** Alembic applies the database migrations in `migrations/versions/`, which create the tables `users` and `profiles` (0001) and `sessions` (0002). Run it again whenever new migrations are added; tables that are already up to date are left alone.

**Check:** the output says `Running upgrade -> 0001` and `0001 -> 0002` (first time) or nothing new, and:
```powershell
.venv\Scripts\alembic.exe current          # expected: 0002 (head)
```

---

## Step 7: Start the backend (terminal 1)

Still in `fastapi-seerver`:
```powershell
.venv\Scripts\fastapi.exe dev app/main.py --port 8002
```

**Why:** this runs the API **and the OAuth 2.0 client** (`/auth/login`, `/auth/callback`, `/auth/logout`). `dev` reloads it automatically when you change code. Leave this terminal open: its logs show every request.

**Check**, in a **new** terminal:
```powershell
Invoke-RestMethod http://localhost:8002/health          # status: ok
Invoke-RestMethod http://localhost:8002/api/users/      # a list (empty on a fresh setup): reading is public
```
Also open http://localhost:8002/docs to see every endpoint. Writing without a session is refused with **401**, which is correct.

---

## Step 8: Start the frontend (terminal 2)

Open a **second** terminal:
```powershell
cd C:\monorepo\auth\oauth2-bff-python\frontend
npm install          # once (and after package.json changes)
npm run dev
```

**Why:** Vite serves the React app **and forwards `/api` and `/auth` to FastAPI** (see `vite.config.ts`), so the browser only ever talks to one origin. That keeps the session cookie first-party and needs no CORS. It must run on port **5175**, because Keycloak only sends users back to `http://localhost:5175/auth/callback`.

**Check:** the output shows `Local: http://localhost:5175/`, and the proxy works:
```powershell
Invoke-RestMethod http://localhost:5175/api/users/     # same list as in step 7, now via the site's own origin
```

---

## Step 9: Use it

1. Open **http://localhost:5175**. You're a **guest**: lists are visible, with no edit buttons.
2. **Sign in → Log in**: on Keycloak's page, enter `alice` / `alice123` (or `alice@example.com`). The browser goes to Keycloak, back to `/auth/callback`, then home, signed in ("FastAPI says you are alice").
3. Create a user and a profile, edit them, delete them. Creating the same username twice shows "Already exists".
4. **Log out**, then **Sign in → Register**: create your own account. You come back signed in as that user.

What happens behind the scenes: Keycloak checks the password and sends a one-time **code** back through the browser. FastAPI exchanges the code for tokens **server-to-server** (with its client secret), verifies the ID token, stores a **session** in Postgres, and gives the browser only a random **HttpOnly cookie** (`bff_session`). Every change is sent with that cookie plus an `X-CSRF: 1` header.

5. Look for yourself: dev tools → Application → Cookies → `localhost:5175` shows `bff_session` (HttpOnly). Local Storage is empty, and no response contains a token.

---

## Step 10 (optional): Run the tests

```powershell
cd C:\monorepo\auth\oauth2-bff-python\fastapi-seerver
.venv\Scripts\python.exe -m pytest            # backend: 10 tests, no Docker or Keycloak needed

cd ..\frontend
npm test                                      # frontend: 5 tests
npm run build                                 # strict TypeScript check
```

---

## Stopping

| What | Command | Data kept? |
|---|---|---|
| Backend / frontend | **Ctrl+C** in terminal 1 / terminal 2 | yes |
| Pause Docker (Postgres + Keycloak) | `docker compose stop` (in the project folder) | yes |
| Remove the containers | `docker compose down` | **yes** (the data lives in the `pg-data` volume) |
| Wipe everything and start over | `docker compose down -v` | **no**: deletes all accounts and app data. Then redo steps 3–6 |

## Next time (everything already installed)

```powershell
cd C:\monorepo\auth\oauth2-bff-python
docker compose up -d                                        # step 3 + 4
cd fastapi-seerver
.venv\Scripts\alembic.exe upgrade head                      # step 6 (only does something if there are new migrations)
.venv\Scripts\fastapi.exe dev app/main.py --port 8002       # step 7, terminal 1
# terminal 2:
cd C:\monorepo\auth\oauth2-bff-python\frontend; npm run dev   # step 8
```

## If a step fails

| Step | Problem | Fix |
|---|---|---|
| 3 | `docker: ... cannot connect` | start Docker Desktop and wait until it says "Engine running" |
| 3 | port 5436 already in use | another program uses it. Change `5436:5432` in `docker-compose.yml` **and** the port in `fastapi-seerver\.env` (`DATABASE_URL`) |
| 4 | the issuer check never answers | `docker compose logs keycloak`. Is `db` healthy (step 3)? |
| 5 | `uv` not found | use the `py -3.12 ...` variants, or install uv: `winget install astral-sh.uv` |
| 6 | `connection refused` | the database isn't running: back to step 3 |
| 7 | 500 errors / `relation "users" does not exist` | step 6 wasn't run |
| 8 | the page says "Could not reach the backend at /api" | FastAPI (step 7) isn't running on 8002 |
| 9 | Keycloak says "Invalid parameter: redirect_uri" | the site isn't on port 5175 (step 8), or `APP_URL` in `fastapi-seerver\.env` was changed |
| 9 | back on the site with a 400 "Code exchange with Keycloak failed" | `OIDC_CLIENT_SECRET` in `fastapi-seerver\.env` doesn't match client `bff` |
| 9 | 400 "Invalid or expired login" | took over 10 min, or cookies blocked: start again from Sign in |

More in the [README troubleshooting table](README.md#troubleshooting).
