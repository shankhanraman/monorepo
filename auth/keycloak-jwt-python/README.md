# Keycloak JWT lab

The same small website as `../keykloak-python` (users and profiles, full CRUD), secured with **plain Keycloak**:
- **Guests can browse.** Lists and details are public.
- **Signing in unlocks create, edit and delete.**
- **Sign in → Log in:** Keycloak's login page, with **username or email** + password.
- **Sign in → Register:** Keycloak's sign-up page. You come back already signed in.

Keycloak issues a **JWT access token**. The React app sends it to FastAPI, which checks the signature, issuer, audience and expiry. The API never sees a password.

```
Browser → React (:5174) → Sign in → Keycloak login page (:8081) → code + PKCE → JWT
React → FastAPI (:8001) with "Authorization: Bearer <JWT>" → FastAPI checks it against Keycloak's public keys
```

## How this differs from `keykloak-python`

| | `keykloak-python` | **this project** |
|---|---|---|
| How users prove who they are | Kerberos ticket (passwordless) or password | password on Keycloak's page |
| Extra infrastructure | Kerberos KDC container, keytab, `keycloak-init` | none |
| Machine setup | hosts entry, MIT Kerberos, Firefox settings, **admin rights** | **nothing, no admin rights** |
| Login with email | off (it broke registration because of the Kerberos provider) | **on** |
| Keycloak / realm | `keycloak.lab.local:8080` / `lab` | `localhost:8081` / `jwt-lab` |
| API / frontend / Postgres ports | 8000 / 5173 / 5434 | 8001 / 5174 / 5435 |
| Backend and frontend code | | **identical**, only URLs and ports differ |

Different ports and realm names mean **both labs can run at the same time**.

| Folder / file | What it is |
|---|---|
| `docker-compose.yml` | Postgres (`db`) and Keycloak |
| `keycloak/jwt-lab-realm.json` | The whole realm: client `frontend` (public, PKCE), audience `fastapi-server`, registration on, login by username or email, demo user **`alice` / `alice123`**. Keycloak requires the file name `<realm>-realm.json` |
| `postgres/` | `create-databases.sql`: roles and databases `app` + `keycloak` |
| `.env.example` | Compose settings: where Postgres runs, DB passwords. Copy to `.env` (gitignored) |
| `fastapi-seerver/` | API: `GET` on `/users` and `/profiles` is public; `POST`/`PUT`/`DELETE` and `/me` need a valid token. Design docs in [fastapi-seerver/docs/](fastapi-seerver/docs/) |
| `frontend/` | React + TypeScript (Vite), organized by feature: `auth/` (Sign in menu, API calls), `me/`, `users/`, `profiles/` |

**New here? Start with [GETTING-STARTED.md](GETTING-STARTED.md)** (step by step, with checks).

> Lab only: plain HTTP, `sslRequired: none`, hardcoded passwords, a seeded demo user. Don't reuse these settings anywhere real.

## Quick setup (one command, no admin rights)

Start Docker Desktop, then:

```powershell
cd fastapi-seerver
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

[scripts/setup-local-dev.ps1](fastapi-seerver/scripts/setup-local-dev.ps1):
1. creates the `.env` files and starts Postgres and Keycloak;
2. waits until realm `jwt-lab` answers;
3. builds the backend `.venv` and creates the tables (`alembic upgrade head`);
4. runs `npm install`;
5. starts FastAPI (:8001) and Vite (:5174) **in the same terminal** (Ctrl+C stops both), then opens http://localhost:5174 in your default browser.

It's safe to re-run: finished steps are skipped.

### macOS / Linux

Same steps with the bash version (no sudo needed: this lab has no Kerberos):
```bash
cd fastapi-seerver
bash scripts/setup-local-dev.sh            # or: --no-start
```
It opens http://localhost:5174 in your default browser. Manual commands are the same as on Windows, with `.venv/bin/` instead of `.venv\Scripts\` (see [GETTING-STARTED.md](GETTING-STARTED.md)).

> **Status on macOS:** written for macOS (bash 3.2, the version Apple ships). Its logic was tested in Linux containers under bash 3.2: start and Ctrl+C cleanup, and the parts every OS shares (Docker, Python, npm). It hasn't been run on a real Mac yet. If a step fails there, the message says which one.

## Manual run

Step by step, with a check after each step and what to do if it fails: **[GETTING-STARTED.md](GETTING-STARTED.md)**. The short version:

```bash
cp .env.example .env                       # first time only
docker compose up -d                       # Postgres :5435 + Keycloak :8081

cd fastapi-seerver
cp .env.example .env                       # first time only
pip install -r requirements.txt
alembic upgrade head
fastapi dev app/main.py --port 8001        # http://localhost:8001/docs

cd ../frontend
npm install
npm run dev                                # http://localhost:5174
```

Admin console: http://localhost:8081 (admin / admin), realm **jwt-lab**.

## Use the site

1. Open http://localhost:5174. You're a **guest**: you see the lists, with no edit buttons.
2. **Sign in → Log in** with `alice` / `alice123`, or `alice@example.com` / `alice123`. You come back signed in, the page shows "FastAPI says you are alice", and the Create / Edit / Delete buttons appear.
3. **Sign in → Register**: fill in Keycloak's form, and you come back signed in as the new user.
4. **Log out** ends the Keycloak session, so the next login asks for the password again.

## Two kinds of "user"

| | Created by | Lives in | Can log in? |
|---|---|---|---|
| **Account** (alice, registered users) | the realm import, or Sign in → Register | Postgres database `keycloak` | yes |
| **App user / profile** (the CRUD data) | any signed-in person, from the page | Postgres database `app` | no: it's data, not an account |

> Any signed-in account can edit or delete **any** record; there are no owners or roles yet. See [docs/architecture.md](fastapi-seerver/docs/architecture.md#6-known-gaps-and-risks).

## Database (PostgreSQL)

One Postgres server, **two databases**, each owned by its own role, and each role can only connect to its own database. It's a Docker container on **5435** by default. To use an installed Postgres or AWS RDS instead, change only `.env` (`COMPOSE_PROFILES`, `KC_DB_URL`) and `fastapi-seerver/.env` (`DATABASE_URL`), then once run:
```bash
psql -h <host> -p <port> -U <admin> -d postgres -v app_password=app -v keycloak_password=keycloak -f postgres/create-databases.sql
```
The same three-mode table as in `../keykloak-python/README.md` ("Database") applies, with this project's ports.

Look at the data:
```bash
docker compose exec db psql -U app -d app -c "select * from users"
docker compose exec db psql -U keycloak -d keycloak -c "select username, email from user_entity where realm_id = (select id from realm where name = 'jwt-lab')"
```

**Start completely fresh** (also needed to apply edits to `jwt-lab-realm.json`, which is only imported on the first start):
```bash
docker compose down -v && docker compose up -d
cd fastapi-seerver && alembic upgrade head
```

## Tests

```bash
cd fastapi-seerver && pytest       # token checks, public reads vs. 401 on every write, CRUD + cascade + 409 (SQLite, no Docker)
cd frontend && npm test            # UserForm (create/edit/error), SignInMenu (Log in / Register / Log out)
cd frontend && npm run build       # strict TypeScript check
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| Setup stops at "Keycloak not ready" | `docker compose logs keycloak`. A common cause is a realm file not named `jwt-lab-realm.json` |
| "Invalid parameter: redirect_uri" on the Keycloak page | the app isn't on http://localhost:5174 (e.g. Vite picked another port because 5174 was busy) |
| FastAPI 401 `Invalid issuer` | the token came from another Keycloak, e.g. the other lab on :8080. Log out and in again on this app |
| FastAPI 401 `Audience doesn't match` | the audience mapper is missing on the `frontend` client |
| FastAPI 500 / `OperationalError` | Postgres isn't reachable at `DATABASE_URL`: `docker compose ps db` (port 5435) |
| `relation "users" does not exist` | tables not created yet: `alembic upgrade head` in `fastapi-seerver/` |
| Create user → `Already exists (username and email must be unique)` | expected: usernames and emails are unique (409) |
| Edits to `jwt-lab-realm.json` don't apply | the realm is only imported on first start: `docker compose down -v` |
