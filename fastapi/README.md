# Items CRUD (FastAPI + your local PostgreSQL)

A simple REST API to create, read, update and delete **items**, stored in the **PostgreSQL 17 installed on this PC** (`localhost:5432`).
On first start it creates the database `crud_app` and the table `items` by itself; there's nothing to set up in Postgres.

```
app/
├── main.py            # FastAPI app; on startup creates the database + table if missing; /health
├── dependencies.py    # settings from .env, database connection, get_db (one session per request)
├── models/items.py    # ItemRow (the table) + ItemCreate / Item (what the API accepts / returns)
├── services/items.py  # the actual list / get / create / update / delete logic
└── routers/items.py   # the /items endpoints
tests/                 # run on an in-memory SQLite database: no Postgres or password needed
```

## Setup, step by step (Windows PowerShell)

**1. Go to the folder**
```powershell
cd C:\monorepo\fastapi
```

**2. Create `.env` and put your Postgres password in it**
```powershell
Copy-Item .env.example .env
notepad .env
```
Fill in `DB_PASSWORD=` with the password of the `postgres` user (the one chosen when PostgreSQL was installed). Save and close.
`.env` is in `.gitignore`, so your password never gets committed. Special characters in the password are fine; no escaping is needed.

**3. Create the Python environment and install packages (once)**
```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```
(Without `uv`: `py -3.12 -m venv .venv`, then `.venv\Scripts\python.exe -m pip install -r requirements.txt`.)

**4. Start the API**
```powershell
.venv\Scripts\fastapi.exe dev app/main.py
```
The first start creates the database `crud_app` and the table `items` on your PostgreSQL 17.
If port 8000 is taken (e.g. by another lab), add `--port 8010`.

**5. Try it:** open **http://localhost:8000/docs**. Each endpoint has a **Try it out** button.

## macOS / Linux

The same app runs unchanged. Only the commands and your local Postgres differ:

```bash
cd ~/…/monorepo/fastapi                 # wherever you cloned it
cp .env.example .env && open -e .env    # (Linux: nano .env)
uv venv --python 3.12 .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt
#   without uv: python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/fastapi dev app/main.py       # http://localhost:8000/docs
.venv/bin/python -m pytest              # tests
```

What to put in `.env` depends on how Postgres is installed on the Mac:

| Postgres on the Mac | `DB_USER` | `DB_PASSWORD` | Look at the data |
|---|---|---|---|
| **Homebrew** (`brew install postgresql@17 && brew services start postgresql@17`) | your macOS username (`whoami`). Homebrew creates no `postgres` user | leave **empty** (local connections are trusted) | `psql -d crud_app -c "select * from items"` |
| **Postgres.app** | your macOS username | leave **empty** | `/Applications/Postgres.app/Contents/Versions/latest/bin/psql -d crud_app` |
| **EDB installer** (like on Windows) | `postgres` | the password chosen during install | `/Library/PostgreSQL/17/bin/psql -U postgres -d crud_app` |

The port is `5432` in all three cases unless you changed it. An empty `DB_PASSWORD` is fine: the app then connects without one.

## Endpoints

| Method | Path | Body | Result |
|---|---|---|---|
| `POST` | `/items/` | `{"name": "Coffee", "description": "1 kg beans", "price": "12.50"}` | **201** the new item |
| `GET` | `/items/?limit=50&offset=0` | | **200** list, oldest first (`limit` 1–100) |
| `GET` | `/items/{id}` | | **200** item, or **404** |
| `PUT` | `/items/{id}` | same as POST (**all fields**: anything left out is cleared) | **200** updated item, or **404** |
| `DELETE` | `/items/{id}` | | **204**, or **404** |
| `GET` | `/health` | | **200** `{"status": "ok"}` |

Rules (invalid input → **422** with a message):
- `name`: required, 1–100 characters;
- `description`: optional, up to 1000 characters;
- `price`: required, ≥ 0, at most 2 decimals.

`price` is stored as an exact decimal (`NUMERIC(10,2)`), never as a float, so it's returned as a string such as `"12.50"`.

From PowerShell instead of the browser:
```powershell
Invoke-RestMethod -Method Post http://localhost:8000/items/ -ContentType application/json -Body '{"name":"Coffee","price":"12.50"}'
Invoke-RestMethod http://localhost:8000/items/
```

## Look at the data in Postgres

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d crud_app -c "select * from items"
```
(It asks for the `postgres` password. `psql` isn't on your PATH, hence the full path.)

## Tests

```powershell
.venv\Scripts\python.exe -m pytest
```
4 tests: the full create/read/update/delete cycle, 404s, validation (422), and paging. They use an in-memory SQLite database, so they don't touch your Postgres.

## Good to know

- **Schema changes:** the app only creates *missing* tables (`create_all`). If you later change a column in `models/items.py`, an existing table isn't altered. Either drop the table (`drop table items;`) in a lab, or add **Alembic** migrations (as the projects under `../auth/` do).
- **The app connects as the `postgres` superuser**, which is fine on your own PC. For anything shared, create a dedicated user that owns only `crud_app` and put that in `.env` instead.
- **PostgreSQL 16** also runs on this PC, on port **5433**. To use it, set `DB_PORT=5433` (and that server's password).

## Troubleshooting

| Problem | Fix |
|---|---|
| Startup fails: `Cannot connect to PostgreSQL at localhost:5432 as 'postgres' … password authentication failed` | wrong `DB_PASSWORD` in `.env` |
| `… connection refused` | PostgreSQL 17 isn't running: Windows Services → `postgresql-x64-17` → Start (it normally starts automatically) |
| `fastapi.exe` not found | step 3 wasn't done in this folder |
| Port 8000 already in use | `.venv\Scripts\fastapi.exe dev app/main.py --port 8010` |
| A changed column doesn't show up | see "Schema changes" above |
