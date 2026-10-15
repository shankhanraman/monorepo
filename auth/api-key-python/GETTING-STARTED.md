# Getting started, step by step

Start the API Key lab **by hand, one piece at a time**, on Windows (PowerShell), with a check after each step.
In a hurry? `fastapi-seerver\scripts\setup-local-dev.ps1` does it all in one go (see [README.md](README.md)).

What you'll end up with:

| Piece | Address | Runs in |
|---|---|---|
| PostgreSQL | `localhost:5438` | Docker |
| FastAPI (backend) | http://localhost:8004 | terminal 1 |
| React site (frontend) | http://localhost:5177 | terminal 2 |

There is **no Keycloak** in this lab: an API key is its own credential.

> **macOS / Linux:** same steps, with `.venv/bin/...` instead of `.venv\Scripts\...`, and `cp` instead of `Copy-Item`.
> Or run it all: `bash fastapi-seerver/scripts/setup-local-dev.sh`.

## Step 1: Settings files (once)

```powershell
cd auth\api-key-python
Copy-Item .env.example .env
Copy-Item fastapi-seerver\.env.example fastapi-seerver\.env
```

## Step 2: Start the database

```powershell
docker compose up -d
docker compose ps db        # wait for (healthy)
```

On first start it runs `postgres/create-databases.sql` to create the `app` database and role.

## Step 3: Backend environment (once)

```powershell
cd fastapi-seerver
uv venv --python 3.12 .venv                                           # or: py -3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt  # or: .venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Step 4: Create tables + seed the demo keys

```powershell
.venv\Scripts\alembic.exe upgrade head
```

Migration `0001` creates `users`/`profiles`; `0002` creates `api_keys` and **seeds two demo keys**.
Check:

```powershell
docker compose -f ..\docker-compose.yml exec db psql -U app -d app -c "select name, prefix, active from api_keys"
# demo (active), revoked-demo (inactive)
```

## Step 5: Start the backend (terminal 1)

```powershell
.venv\Scripts\fastapi.exe dev app/main.py --port 8004
```

Check (new terminal):

```powershell
Invoke-RestMethod http://localhost:8004/health          # status: ok
Invoke-RestMethod http://localhost:8004/users/          # a list (public read)
```

A write without a key is refused with **401** — correct. Open http://localhost:8004/docs for all endpoints.

## Step 6: Start the frontend (terminal 2)

```powershell
cd ..\frontend
npm install        # once
npm run dev        # http://localhost:5177
```

## Step 7: Use it

1. Open http://localhost:5177 — you're a **guest** (lists visible, no edit buttons).
2. **Use API key** → paste `mial_live_demo_do_not_use_in_prod` → the page shows "FastAPI accepted key demo"
   and the Create / Edit / Delete buttons appear.
3. Create / edit / delete users and profiles.
4. **Forget key** → back to guest. Paste the revoked key (`mial_live_revoked_example`) → writes return 401.

## Step 8 (optional): Tests

```powershell
cd ..\fastapi-seerver; .venv\Scripts\python.exe -m pytest     # backend: key checks + CRUD (no Docker)
cd ..\frontend; npm test; npm run build                       # frontend tests + strict TypeScript
```

## Stopping / fresh start

| What | Command |
|---|---|
| Backend / frontend | Ctrl+C in each terminal |
| Remove containers (keep data) | `docker compose down` |
| Wipe everything (re-seed keys next time) | `docker compose down -v` then redo steps 2 + 4 |

## If a step fails

| Problem | Fix |
|---|---|
| `docker: cannot connect` | start Docker Desktop, wait for "Engine running" |
| port 5438 in use | change `5438:5432` in `docker-compose.yml` **and** `DATABASE_URL` in `fastapi-seerver\.env` |
| `relation "api_keys" does not exist` | run step 4 (`alembic upgrade head`) |
| write returns 401 with the demo key | make sure step 4 seeded it (check query above) and the key is pasted exactly |
