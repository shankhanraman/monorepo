# Getting started, step by step

How to start the Keycloak JWT lab **by hand, one piece at a time**, on Windows (PowerShell), with a check after each step.
In a hurry? `fastapi-seerver\scripts\setup-local-dev.ps1` does steps 2–8 in one go (see [README.md](README.md)).

What you'll end up with:

| Piece | Address | Runs in |
|---|---|---|
| PostgreSQL | `localhost:5435` | Docker |
| Keycloak (login server) | http://localhost:8081 | Docker |
| FastAPI (backend) | http://localhost:8001 | terminal 1 |
| React site (frontend) | http://localhost:5174 | terminal 2 |

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
cd C:\monorepo\auth\keycloak-jwt-python
```

All commands below start from this folder unless a step says `cd` somewhere else.

---

## Step 2: Create the settings files (once)

```powershell
Copy-Item .env.example .env
Copy-Item fastapi-seerver\.env.example fastapi-seerver\.env
```

**Why:** `.env` holds the passwords and addresses (database, Keycloak). The `.example` files are templates that are committed to git. The real `.env` files are not (they're in `.gitignore`).

**Check:** `Get-Content .env` shows `COMPOSE_PROFILES=local-db` and the database passwords.

---

## Step 3: Start the database

```powershell
docker compose up -d db
```

**Why:** Postgres stores everything: the site's users and profiles (database `app`) and Keycloak's accounts (database `keycloak`). On the **first** start it runs `postgres/create-databases.sql`, which creates both databases and their roles.

**Check:** wait until the status says **(healthy)**:
```powershell
docker compose ps db
```

---

## Step 4: Start Keycloak

```powershell
docker compose up -d keycloak
```

**Why:** Keycloak shows the login and sign-up pages and issues the JWT tokens. On its **first** start it imports `keycloak/jwt-lab-realm.json`: the realm `jwt-lab`, the app's client settings, and the demo user `alice`.

**Check:** the first start takes about 30–60 s. Repeat this until it prints the issuer:
```powershell
(Invoke-RestMethod http://localhost:8081/realms/jwt-lab/.well-known/openid-configuration).issuer
# expected: http://localhost:8081/realms/jwt-lab
```
If it fails, look at the log: `docker compose logs keycloak`

Optional: admin console at http://localhost:8081, `admin` / `admin`, then switch to realm **jwt-lab**.

---

## Step 5: Backend: Python environment (once)

```powershell
cd fastapi-seerver
uv venv --python 3.12 .venv                                        # or: py -3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt   # or: .venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Why:** a separate Python environment (`.venv`) for this project, with FastAPI, PyJWT, SQLAlchemy, Alembic, etc.

**Check:**
```powershell
.venv\Scripts\python.exe -c "import fastapi, jwt, sqlalchemy; print('ok')"
```

> The commands below call `.venv\Scripts\...` directly, so you don't need to "activate" the environment. (If you prefer to activate it and PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` first.)

---

## Step 6: Create the tables

Still in `fastapi-seerver`:
```powershell
.venv\Scripts\alembic.exe upgrade head
```

**Why:** Alembic applies the database migrations in `migrations/versions/`, which create the tables `users` and `profiles`. Run it again whenever new migrations are added; tables that are already up to date are left alone.

**Check:** the output says `Running upgrade -> 0001` (first time) or nothing new, and:
```powershell
.venv\Scripts\alembic.exe current          # expected: 0001 (head)
```

---

## Step 7: Start the backend (terminal 1)

Still in `fastapi-seerver`:
```powershell
.venv\Scripts\fastapi.exe dev app/main.py --port 8001
```

**Why:** this runs the API. `dev` reloads it automatically when you change code. Leave this terminal open: its logs show every request.

**Check**, in a **new** terminal:
```powershell
Invoke-RestMethod http://localhost:8001/health          # status: ok
Invoke-RestMethod http://localhost:8001/users/          # a list (empty on a fresh setup): reading is public
```
Also open http://localhost:8001/docs to see every endpoint. Writing without a login is refused with **401**, which is correct.

---

## Step 8: Start the frontend (terminal 2)

Open a **second** terminal:
```powershell
cd C:\monorepo\auth\keycloak-jwt-python\frontend
npm install          # once (and after package.json changes)
npm run dev
```

**Why:** Vite serves the React app and reloads the browser when you change code. It must run on port **5174**, because that's the only address Keycloak will send users back to.

**Check:** the output shows `Local: http://localhost:5174/`. If it says another port, something else is using 5174: stop it and retry.

---

## Step 9: Use it

1. Open **http://localhost:5174**. You're a **guest**: lists are visible, with no edit buttons.
2. **Sign in → Log in**: on Keycloak's page, enter `alice` / `alice123` (or `alice@example.com`). You come back signed in, and the page shows "FastAPI says you are alice".
3. Create a user and a profile, edit them, delete them. Creating the same username twice shows "Already exists".
4. **Log out**, then **Sign in → Register**: create your own account. You come back signed in as that user.

What happens behind the scenes: Keycloak checks the password and gives the browser a **JWT**. The site sends it with every change (`Authorization: Bearer …`), and FastAPI verifies it with Keycloak's public keys.

---

## Step 10 (optional): Run the tests

```powershell
cd C:\monorepo\auth\keycloak-jwt-python\fastapi-seerver
.venv\Scripts\python.exe -m pytest            # backend: 3 tests, no Docker needed

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
cd C:\monorepo\auth\keycloak-jwt-python
docker compose up -d                                        # step 3 + 4
cd fastapi-seerver
.venv\Scripts\alembic.exe upgrade head                      # step 6 (only does something if there are new migrations)
.venv\Scripts\fastapi.exe dev app/main.py --port 8001       # step 7, terminal 1
# terminal 2:
cd C:\monorepo\auth\keycloak-jwt-python\frontend; npm run dev   # step 8
```

## If a step fails

| Step | Problem | Fix |
|---|---|---|
| 3 | `docker: ... cannot connect` | start Docker Desktop and wait until it says "Engine running" |
| 3 | port 5435 already in use | another program uses it. Change `5435:5432` in `docker-compose.yml` **and** the port in `fastapi-seerver\.env` (`DATABASE_URL`) |
| 4 | the issuer check never answers | `docker compose logs keycloak`. Is `db` healthy (step 3)? |
| 5 | `uv` not found | use the `py -3.12 ...` variants, or install uv: `winget install astral-sh.uv` |
| 6 | `connection refused` | the database isn't running: back to step 3 |
| 7 | 500 errors / `relation "users" does not exist` | step 6 wasn't run |
| 9 | Keycloak says "Invalid parameter: redirect_uri" | the site isn't on port 5174 (step 8) |
| 9 | "FastAPI rejected the token" | the backend isn't running, or its `.env` points at another Keycloak |

More in the [README troubleshooting table](README.md#troubleshooting).
