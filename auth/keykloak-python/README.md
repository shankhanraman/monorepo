# Kerberos → Keycloak → FastAPI lab

A small website with users and profiles (full CRUD):
- **Guests can browse.** Lists and details are public.
- **Signing in unlocks create, edit and delete.**
- **The Sign in menu** has two options:
  - **Log in:** Kerberos users with a ticket get in **without typing a password**; everyone else uses the password form.
  - **Register:** Keycloak's sign-up form creates a new account (password login).

How the Kerberos login works under the hood:

```
kinit alice ──► KDC issues TGT
Browser → React (localhost:5173) → redirect to Keycloak
Keycloak: "401 WWW-Authenticate: Negotiate"
Browser gets a service ticket for HTTP/keycloak.lab.local from the KDC → sends it to Keycloak (SPNEGO)
Keycloak decrypts it with its keytab → alice is logged in → JWT back to React
React → FastAPI with "Authorization: Bearer <JWT>" → FastAPI checks it against Keycloak's JWKS
```

**FastAPI never touches Kerberos.** It only checks JWT signature, `iss`, `aud` and `exp` ([app/dependencies.py](fastapi-seerver/app/dependencies.py)).

| Folder / file | What it is |
|---|---|
| `kdc/` | MIT Kerberos KDC, realm `LAB.LOCAL`. Creates `alice` / `alice123` and Keycloak's service principal `HTTP/keycloak.lab.local`, and exports its keytab |
| `krb5.conf` | Where the KDC for `LAB.LOCAL` lives (used by the KDC and Keycloak containers) |
| `keycloak/lab-realm.json` | Realm `lab`: Kerberos user federation, public PKCE client `frontend`, audience `fastapi-server` |
| `docker-compose.yml` | Runs Postgres (`db`), the KDC, Keycloak, and `keycloak-init` (one-shot settings, see below) |
| `postgres/` | `create-databases.sql`: roles and databases `app` + `keycloak` (used by the container, or run by hand on an installed server/RDS) |
| `.env.example` | Compose settings: where Postgres runs, DB passwords. Copy to `.env` (gitignored) |
| `keycloak/init.sh` | After import: turns on the Kerberos login step, turns off the profile check, enables self-registration |
| `fastapi-seerver/` | API: `GET` on `/users` and `/profiles` is public; `POST`/`PUT`/`DELETE` and `/me` need a valid token. Design docs in [fastapi-seerver/docs/](fastapi-seerver/docs/) |
| `frontend/` | React + TypeScript (Vite), organized by feature: `auth/` (Sign in menu, API calls), `me/`, `users/`, `profiles/` |

> Lab only: plain HTTP, `sslRequired: none`, hardcoded passwords. Don't reuse these settings anywhere real.

## Quick setup (one command)

Start Docker Desktop, then from `fastapi-seerver/`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1            # logs in as alice
powershell -ExecutionPolicy Bypass -File scripts\setup-local-dev.ps1 -User bob   # another Kerberos user
```

[scripts/setup-local-dev.ps1](fastapi-seerver/scripts/setup-local-dev.ps1) does sections 1 to 3 below:
- installs MIT Kerberos and Firefox, then writes `krb5.ini`, the hosts entry and Firefox's Kerberos prefs (one admin prompt)
- starts the containers, builds `.venv`, runs `npm install`
- runs `kinit` (asks for the password)
- starts FastAPI and Vite in the same terminal (Ctrl+C stops both), then opens Firefox

It's safe to re-run: finished steps are skipped. The sections below explain what each step does, and are the manual way to do it.

## macOS

`setup-local-dev.ps1` is Windows-only. On a Mac (Docker Desktop for Mac, Apple Silicon or Intel) use the bash version:

```bash
cd fastapi-seerver
bash scripts/setup-local-dev.sh                 # as alice
bash scripts/setup-local-dev.sh --user bob      # another Kerberos user
bash scripts/setup-local-dev.sh --no-start      # setup only
```

It does the same as the Windows script, adapted to macOS. It asks for **your Mac password once** (`sudo`), for `/etc/hosts` and `/etc/krb5.conf`.

| Step | Windows (`.ps1`) | macOS (`.sh`) |
|---|---|---|
| Kerberos client | install MIT Kerberos (winget) | **nothing to install**: macOS has Kerberos built in (Heimdal `kinit` / `klist`) |
| Kerberos config | `C:\ProgramData\MIT\Kerberos5\krb5.ini` | `/etc/krb5.conf`, copied from [krb5.conf.mac](krb5.conf.mac). **An existing file is backed up** as `/etc/krb5.conf.backup-<date>` |
| Hosts entry | `C:\Windows\System32\drivers\etc\hosts` (UAC prompt) | `/etc/hosts`, for **both `127.0.0.1` and `::1`**: macOS treats `*.local` as Bonjour names, and an IPv4-only entry can stall each lookup ~5 s |
| Browser | Firefox autoconfig (MIT GSSAPI) | **Safari:** usually nothing. **Chrome:** the script sets `AuthServerAllowlist=keycloak.lab.local` (restart Chrome, check `chrome://policy`). **Firefox:** `about:config` → `network.negotiate-auth.trusted-uris` = `keycloak.lab.local` |
| Python venv | `.venv\Scripts\…` | `.venv/bin/…` |

Manual steps on a Mac: the same as section 2 below, with `.venv/bin/` instead of `.venv\Scripts\`. Then:
```bash
kinit alice@LAB.LOCAL      # password alice123
klist                      # after logging in on the site: also shows HTTP/keycloak.lab.local@LAB.LOCAL
```

**Undo the Mac changes** when you're done with the lab:
- restore your backup: `sudo mv /etc/krb5.conf.backup-<date> /etc/krb5.conf` (or `sudo rm /etc/krb5.conf` if there was none);
- remove the two `lab.local` lines from `/etc/hosts`;
- `defaults delete com.google.Chrome AuthServerAllowlist`;
- `kdestroy`.

> **Status on macOS:** written for macOS (bash 3.2, the version Apple ships). Its logic was tested in Linux containers under bash 3.2: start and Ctrl+C cleanup, and the parts every OS shares (Docker, Python, npm). It hasn't been run on a real Mac yet. If a step fails there, the message says which one.

The Mac Kerberos config itself is tested: `krb5.conf.mac` was used by real Heimdal `kinit` (the implementation macOS ships) to get a ticket from the lab's KDC over TCP.

## 1. One-time Windows setup

1. **Hosts file** (`C:\Windows\System32\drivers\etc\hosts`, edit as admin):
   ```
   127.0.0.1 keycloak.lab.local kdc.lab.local
   ```
   Kerberos ties the service principal to a hostname, so Keycloak must be reached as `keycloak.lab.local`, not `localhost`.

2. **MIT Kerberos for Windows** (`kinit`/`klist`): install from https://web.mit.edu/kerberos/dist/. Put this in `C:\ProgramData\MIT\Kerberos5\krb5.ini`:
   ```ini
   [libdefaults]
       default_realm = LAB.LOCAL
       dns_lookup_kdc = false
       dns_canonicalize_hostname = false
       rdns = false
       udp_preference_limit = 1
   [realms]
       LAB.LOCAL = {
           kdc = 127.0.0.1
       }
   [domain_realm]
       .lab.local = LAB.LOCAL
       keycloak.lab.local = LAB.LOCAL
   ```
   A Java JDK on PATH also ships `kinit`/`klist`, and Windows has its own `klist`. Call the MIT ones by full path (`& "C:\Program Files\MIT\Kerberos\bin\kinit.exe"`).

3. **Firefox** (`about:config`):
   - `network.negotiate-auth.trusted-uris` = `keycloak.lab.local`
   - `network.auth.use-sspi` = `false` (use MIT Kerberos instead of Windows SSPI)
   - `network.negotiate-auth.gsslib` = `C:\Program Files\MIT\Kerberos\bin\gssapi64.dll` (the MIT library to use)

   Chrome and Edge always use Windows SSPI, which only works on a domain-joined PC. They get Keycloak's password form instead, which still checks the password against the KDC.

## 2. Run it

```bash
# Postgres + KDC + Keycloak (Docker Desktop must be running)
cp .env.example .env                       # first time only
docker compose up --build

# FastAPI (new terminal)
cd fastapi-seerver
cp .env.example .env                       # first time only
pip install -r requirements.txt
alembic upgrade head                       # create/upgrade the app's tables
fastapi dev app/main.py            # http://localhost:8000

# React (new terminal)
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

`keycloak-init` is a one-shot container that runs [keycloak/init.sh](keycloak/init.sh) after Keycloak starts, because a realm import can't set these things:
- turns the **Kerberos** step of the browser login flow on (import leaves it Disabled, which means always the password form)
- turns off the "verify profile" check (Kerberos gives no first/last name, so every first login would stop at a profile form)
- enables **self-registration** with login by username only (see "Register" below for why email login stays off)

`docker compose logs keycloak-init` should end with `Self-registration enabled (login by username)`. Admin console: http://keycloak.lab.local:8080 (admin / admin).

**Everything is stored in PostgreSQL** (next section), so accounts and app data survive restarts. As a result `keycloak/lab-realm.json` is imported **only on the first start**. To apply edits to it, or to start completely fresh (this wipes the database, i.e. all accounts and app data, and the KDC):
```bash
docker compose down -v && docker compose up -d --build
cd fastapi-seerver && alembic upgrade head
```

## Database (PostgreSQL)

One Postgres server, **two databases**, each owned by its own role, and each role can only connect to its own database:

| Database | Role | Holds | Created by |
|---|---|---|---|
| `app` | `app` | the site's users and profiles | `postgres/create-databases.sql` + **`alembic upgrade head`** (tables) |
| `keycloak` | `keycloak` | all login accounts (registered + copies of Kerberos users), sessions, realm settings | `postgres/create-databases.sql`; Keycloak creates its own tables |

**Where Postgres runs is configuration only.** Edit two files, `.env` (Compose and Keycloak, which run *inside* Docker) and `fastapi-seerver/.env` (FastAPI, which runs on your PC):

| Mode | `.env` | `fastapi-seerver/.env` | One-time setup |
|---|---|---|---|
| **Docker container** (default) | `COMPOSE_PROFILES=local-db`<br>`KC_DB_URL=jdbc:postgresql://db:5432/keycloak` | `DATABASE_URL=postgresql+psycopg://app:app@localhost:5434/app` | none: created on first `docker compose up` (published on **5434**, because 5432/5433 are used by Postgres servers installed on this PC) |
| **Installed Postgres** | delete `COMPOSE_PROFILES`<br>`KC_DB_URL=jdbc:postgresql://host.docker.internal:5432/keycloak` | `…@localhost:5432/app` | run the SQL below as `postgres`. In `pg_hba.conf`, allow Docker's network (e.g. `host keycloak keycloak 0.0.0.0/0 scram-sha-256`), so the Keycloak container can connect |
| **AWS RDS** | delete `COMPOSE_PROFILES`<br>`KC_DB_URL=jdbc:postgresql://<endpoint>:5432/keycloak?sslmode=require` | `…@<endpoint>:5432/app?sslmode=require` | run the SQL below as the master user; the security group must allow your IP on 5432 |

Creating the roles and databases on an installed server or RDS (safe to re-run; passwords must match `.env`):
```bash
psql -h <host> -p <port> -U <admin> -d postgres -v app_password=app -v keycloak_password=keycloak -f postgres/create-databases.sql
```
Then run `alembic upgrade head` from `fastapi-seerver/` and `docker compose up -d`. Only Docker mode was tested end to end; the other two use the same code with different URLs.

Look at the data (Docker mode):
```bash
docker compose exec db psql -U app -d app -c "select * from users"
docker compose exec db psql -U keycloak -d keycloak -c "select username, email from user_entity"
```

Changing the app's tables: edit the `*Row` class in `fastapi-seerver/app/models/`, run `alembic revision --autogenerate -m "what changed"`, review the file in `migrations/versions/`, then `alembic upgrade head`.

## 3. Use the site

Open http://localhost:5173 in Firefox. You start as a **guest**: users and profiles are listed, and there are no edit buttons.

### Sign in → Log in

```bash
kinit alice@LAB.LOCAL     # password: alice123
klist                     # shows krbtgt/LAB.LOCAL@LAB.LOCAL
```

Click **Sign in → Log in**. You come back signed in as `alice` **with no password prompt**, the page shows "FastAPI says you are alice", and the Create / Edit / Delete buttons appear. `klist` now also shows a ticket for `HTTP/keycloak.lab.local@LAB.LOCAL`.

No ticket (`kdestroy`), a non-Firefox browser, or a registered account: Keycloak shows its login form. `alice` / `alice123` works there too; the KDC checks the password.

### Sign in → Register

Click **Sign in → Register** and fill in Keycloak's sign-up form. You come back already signed in as the new user. Things to know:
- **Log in with the username, not the email.** Keycloak's Kerberos connector treats `name@other-domain` as a Kerberos name in an unknown realm, so email login (and, if it were on, every sign-up) fails with "Unexpected error".
- The new account lives **in Keycloak, not in Kerberos**. Keycloak's Kerberos connector can read the KDC but can't add users to it. So registered users log in with their password, never passwordless.
- A username that already exists in Kerberos (e.g. `alice`) is refused: "Username already exists".

## Three kinds of "user"

| | Created by | Lives in | Logs in with |
|---|---|---|---|
| **Kerberos user** (alice, bob) | admin: `kadmin` (below) | KDC; Keycloak copies it on first login | Kerberos ticket (passwordless) or password |
| **Registered user** | anyone: Sign in → Register | Postgres database `keycloak` | password |
| **App user / profile** (the CRUD data) | any signed-in person, from the page | Postgres database `app` | n/a: it's data, not an account |

Add a Kerberos user:
```bash
docker compose exec kdc kadmin.local -q "addprinc -pw bob123 bob"
kinit bob@LAB.LOCAL        # or type bob / bob123 into the Keycloak form
```
On bob's first login Keycloak creates `bob` in realm `lab` automatically.

> Any signed-in account can edit or delete **any** record; there are no owners or roles yet. See [docs/architecture.md](fastapi-seerver/docs/architecture.md#6-known-gaps-and-risks).

## Tests

```bash
cd fastapi-seerver && pytest       # token checks, public reads vs. 401 on every write, CRUD + cascade + 409 (in-memory SQLite, no Docker needed)
cd frontend && npm test            # UserForm (create/edit/error), SignInMenu (Log in / Register / Log out)
cd frontend && npm run build       # strict TypeScript check
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| Always the password form, never SPNEGO | Kerberos step not *Alternative*, Firefox prefs not set, no ticket (`klist`), or Keycloak opened as `localhost` instead of `keycloak.lab.local` |
| Keycloak logs `Checksum failed` / `Cannot find key` | Keytab doesn't match the KDC: `docker compose down -v && docker compose up --build` |
| FastAPI 401 `Invalid issuer` | Token came from a different hostname. Browser and FastAPI must both use `keycloak.lab.local:8080` |
| FastAPI 401 `Invalid audience` | Audience mapper missing on the `frontend` client |
| Create user → `email: ... special-use or reserved name` | `EmailStr` rejects reserved domains like `.local`, so use e.g. `carol@example.com`. (Kerberos users' Keycloak email `alice@lab.local` is unaffected: it's only in the token.) |
| `kinit: Cannot contact any KDC` | Port 88 not published, or `krb5.ini` not pointing to `127.0.0.1` |
| Register or Log in → "Unexpected error when handling authentication request" | An email was used as the username, or `loginWithEmailAllowed` was switched back on. Keycloak log: `Kerberos unreachable … Cannot locate KDC` |
| No Edit/Delete buttons | You're a guest: Sign in first |
| Changes to `lab-realm.json` don't apply | The realm is only imported on first start (it's stored in Postgres): `docker compose down -v` |
| FastAPI 500 / `OperationalError` / `connection refused` | Postgres not reachable at `DATABASE_URL`: `docker compose ps db`, check the port (5434 for Docker mode) |
| `relation "users" does not exist` | Tables not created yet: `alembic upgrade head` in `fastapi-seerver/` |
| Create user → `Already exists (username and email must be unique)` | Expected: usernames and emails are unique (409) |
| Keycloak won't start: `Connection to db:5432 refused` / `password authentication failed` | `KC_DB_URL` or `KEYCLOAK_DB_PASSWORD` in `.env` doesn't match the database. For an external DB, run `postgres/create-databases.sql` there first |

Debug logging for the Kerberos provider is on (`debug: true` in the realm JSON): see `docker compose logs keycloak`.
