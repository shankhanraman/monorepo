# API Key lab

The same small website as the other labs (users and profiles, full CRUD), secured with an **API key**:
- **Guests can browse.** Lists and details are public.
- **A valid API key unlocks create, edit and delete.** Send it in the `X-API-Key` header.

The contrast with the Keycloak labs: there is **no identity provider and no login page**. An API key *is* the
credential (like a personal access token or a machine-to-machine key). That makes this the simplest lab of the set.

```
Browser → React (:5177)  --  writes send header  X-API-Key: <key>
React → FastAPI (:8004)   --  FastAPI hashes the key and looks it up in Postgres; active match → allowed
```

## The whole mechanism (one sentence)

**Reads are public; to write, send your key in `X-API-Key`; the server hashes it and looks for an *active* row with that hash; match → allowed, else 401.**

The five files that hold the logic:

| File | What it shows |
|---|---|
| [`app/models/apikeys.py`](fastapi-seerver/app/models/apikeys.py) | the `api_keys` table (`name, prefix, key_hash, active`) and `hash_key()` — we store a **SHA-256**, never the key |
| [`migrations/versions/0002_create_api_keys.py`](fastapi-seerver/migrations/versions/0002_create_api_keys.py) | the table + two **seeded demo keys** (one active, one inactive) |
| [`app/dependencies.py`](fastapi-seerver/app/dependencies.py) | `current_key`: the entire check (hash → look up active row → 401) |
| [`app/routers/users.py`](fastapi-seerver/app/routers/users.py) | how a route opts in: `dependencies=require_login` on writes, reads left open |
| [`frontend/src/auth/`](fastapi-seerver/../frontend/src/auth/) | `apiKey.ts` (store the key), `apiFetch.ts` (send the header), `SignInMenu.tsx` (paste / forget) |

Everything else (`users`/`profiles` services, models, the React CRUD) is the same demo app the other labs use.

## Two seeded keys (documented, lab-only)

Migration `0002` seeds two keys. Only the hash is stored; here is the plaintext:

| Key | Active? | Use |
|---|---|---|
| `mial_live_demo_do_not_use_in_prod` | yes | unlocks create / edit / delete |
| `mial_live_revoked_example` | no | shows the revoked → 401 path |

> Lab only: plain HTTP, keys in the repo, no rate limiting. Don't reuse any of this anywhere real.

## Ports

Different from the other labs, so they can all run at once.

| | this lab |
|---|---|
| API | 8004 |
| Frontend | 5177 |
| Postgres | 5438 |

## Quick setup (one command, no admin rights)

Start Docker Desktop, then:

```powershell
cd fastapi-seerver
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1
```

It creates the `.env` files, starts Postgres, builds the backend `.venv`, runs `alembic upgrade head`
(which **seeds the two demo keys**), runs `npm install`, then starts FastAPI (:8004) and Vite (:5177) in
the same terminal (Ctrl+C stops both) and opens http://localhost:5177. Safe to re-run.

### macOS / Linux

```bash
cd fastapi-seerver
bash scripts/setup-local-dev.sh            # or: --no-start
```

## Manual run

```bash
cp .env.example .env                       # first time only
docker compose up -d                       # Postgres :5438

cd fastapi-seerver
cp .env.example .env                       # first time only
pip install -r requirements.txt
alembic upgrade head                       # tables + seeded demo keys
fastapi dev app/main.py --port 8004        # http://localhost:8004/docs

cd ../frontend
npm install
npm run dev                                # http://localhost:5177
```

## Use the site

1. Open http://localhost:5177. You're a **guest**: you see the lists, no edit buttons.
2. **Use API key** → paste `mial_live_demo_do_not_use_in_prod` → the page reloads, shows
   "FastAPI accepted key demo", and Create / Edit / Delete appear.
3. **Forget key** returns you to guest mode.
4. Try the revoked key (`mial_live_revoked_example`): writes come back 401.

## Verify from a terminal (no browser)

```bash
KEY=mial_live_demo_do_not_use_in_prod
curl -s -o /dev/null -w "%{http_code}\n" localhost:8004/users/                                  # 200 (public read)
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8004/users/ \
  -H 'Content-Type: application/json' -d '{"username":"a","email":"a@example.com"}'              # 401 (no key)
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8004/users/ -H "X-API-Key: $KEY" \
  -H 'Content-Type: application/json' -d '{"username":"a","email":"a@example.com"}'              # 201 (valid)
curl -s -H "X-API-Key: $KEY" localhost:8004/me                                                  # {"name":"demo","prefix":"mial_live"}
```

## Tests

```bash
cd fastapi-seerver && pytest     # key checks (no/wrong/revoked/valid), CRUD + cascade + 409 (SQLite, no Docker)
cd frontend && npm test          # SignInMenu, UserForm
cd frontend && npm run build     # strict TypeScript check
```

## Look at the data / start fresh

```bash
docker compose exec db psql -U app -d app -c "select id, name, prefix, active from api_keys"
docker compose down -v && docker compose up -d      # wipe; re-seed on next `alembic upgrade head`
```

## Security notes (what makes this real-ish)

- **Keys are hashed at rest** (SHA-256) — a database leak doesn't expose usable keys.
- Only a **prefix** is ever shown back (e.g. in `/me`), enough to identify a key without revealing it.
- **Revocation** is a flag (`active`), so a key can be disabled without deleting the row.
- In production you'd also: serve over **HTTPS**, **rate-limit**, protect any key-minting endpoint, and give
  keys an expiry. This lab keeps those out to stay teachable.
