# Architecture

> Scope: the `fastapi-seerver` service and the identity provider it depends on (Keycloak).
> Companion docs: [datamodel.md](datamodel.md) (what data exists), [dataflow.md](dataflow.md) (how requests move) and [deployment.md](deployment.md) (CI/CD, secrets, Kubernetes: target design).
> Status: **learning lab**. Settings marked *lab-only* below must change before anything real runs on this.
> Sibling project: `../../../keykloak-python/` is the same app with **Kerberos** in front of Keycloak. This one is plain Keycloak.

## 1. Purpose

A FastAPI resource server secured with **JWTs issued by Keycloak**.
Users sign in on Keycloak's own login page (username or email + password) or register there. Keycloak issues an **OIDC access token (JWT)**, and the API only verifies that token. It never sees a password.

The main architectural idea: **authentication ends at the identity provider.**
Adding MFA, social login, LDAP or Kerberos (see the sibling project) changes Keycloak's configuration, not this codebase.

It behaves like a normal website:
- **Guests can read.** Users and profiles can be listed and viewed without logging in.
- **Changes need an account.** Create, update and delete require a login.
- **The SPA's Sign in menu** offers **Log in** and **Register**. Both are Keycloak pages; the app shows no login form of its own.

## 2. System context

```mermaid
flowchart LR
    user([User])
    browser[Browser<br/>React SPA :5174]
    kc[Keycloak<br/>realm jwt-lab :8081]
    api[fastapi-seerver<br/>:8001]
    pg[(PostgreSQL :5435<br/>db 'app' + db 'keycloak')]

    user -- "username/email + password<br/>(on Keycloak's page)" --> kc
    browser -- "redirect: login / register" --> kc
    kc -- "OIDC code + PKCE -> JWT" --> browser
    browser -- "Bearer JWT" --> api
    api -- "JWKS (public keys), cached" --> kc
    api -- "SQL as role 'app'" --> pg
    kc -- "JDBC as role 'keycloak'" --> pg
```

| Component | Responsibility | Trusts |
|---|---|---|
| **Keycloak** (`../../keycloak/`) | The identity provider. Owns the login and sign-up pages, password hashes, sessions, token lifetimes and each token's audience. Stores all of it in Postgres database `keycloak` | nothing |
| **PostgreSQL** (`../../postgres/`) | Two isolated databases: `app` (owned by role `app`) and `keycloak` (owned by role `keycloak`). Each role can only connect to its own database. A Docker container by default; an installed server or AWS RDS by configuration (D12) | n/a |
| **fastapi-seerver** | Business API: users and profiles, stored in database `app` | Keycloak only, by checking JWT signatures against Keycloak's published keys |
| **React SPA** (`../../frontend/`) | Sends users to Keycloak, receives tokens (keycloak-js, PKCE), calls the API | nothing; it's a public client and holds no secrets |

Trust is **one-directional and narrow**. The API trusts exactly one issuer, one audience and one algorithm, and never handles credentials.

## 3. Service internals

### 3.1 Layering

```
app/
├── main.py           composition root: app, middleware, router wiring, /health, /me
├── dependencies.py   cross-cutting: settings + authentication (current_user, require_login)
├── db.py             SQLAlchemy engine, session per request (get_db), declarative Base
├── routers/          HTTP layer: paths, status codes, request/response models, get_db injection
├── services/         application logic: SQL through the session, returns Pydantic models
└── models/           per entity: the table (*Row, SQLAlchemy) + the API contract (Pydantic)
migrations/           Alembic: versions/0001_create_users_and_profiles.py, ...
```

```mermaid
flowchart TD
    main[main.py<br/>composition root] --> routers
    main --> deps[dependencies.py<br/>settings, current_user]
    routers[routers/*] --> services[services/*]
    routers --> models[models/*]
    routers -. "Depends(get_db)" .-> db[db.py<br/>engine, get_db, Base]
    services --> models
    models --> db
    db --> deps
    routers -. "require_login on write endpoints" .-> deps
```

Dependency rules, which the code follows today and new code should keep:

1. **`models` depend only on Pydantic, SQLAlchemy and `db.Base`.** Each file holds one entity's table (`UserRow`) and API schemas (`UserCreate`, `User`).
2. **`services` don't know about HTTP.** No `HTTPException`, no `Request`. They take a `Session`, return Pydantic models (never ORM rows), and return `None`/`False` for "not found", which the router turns into a 404.
3. **`routers` don't run SQL**; they get a session from `get_db` and pass it to services.
4. **Integrity rules live in the database, friendly errors in the app.**
   - Unique `username`/`email`, the profile → user foreign key and `ON DELETE CASCADE` are **constraints in Postgres** ([migrations/versions/0001_create_users_and_profiles.py](../migrations/versions/0001_create_users_and_profiles.py)), so they hold for every writer and under concurrency.
   - The routers still pre-check "user exists" before writing a profile, for a clear 404. A unique violation becomes a 409 through one `IntegrityError` handler in `main.py`.
5. **Schema changes only through Alembic.** Change a `*Row` class → `alembic revision --autogenerate` → review → `alembic upgrade head`. The app never calls `create_all` (only the tests do, on SQLite).
6. **Reads are public; writes declare `dependencies=require_login`.** Every `POST`/`PUT`/`DELETE` lists it in its decorator ([routers/users.py](../app/routers/users.py)). This is **opt-in per endpoint**: a new write endpoint without it is public. Reviews must check for it, and [tests/test_auth.py](../tests/test_auth.py) asserts 401 on every write endpoint, so extend that list when adding one.

### 3.2 Authentication component

[`current_user`](../app/dependencies.py) is the only security-critical code in the service:

| Check | How | Fails as |
|---|---|---|
| Header present, `Bearer` scheme | `HTTPBearer()` | 401 (403 on older FastAPI versions) |
| Signature, and key chosen by `kid` | `PyJWKClient` → Keycloak `/protocol/openid-connect/certs` | 401 |
| Algorithm pinned to `RS256` | `algorithms=["RS256"]` (blocks `alg=none` and HS/RS confusion attacks) | 401 |
| Issuer = `KEYCLOAK_ISSUER` | `issuer=` | 401 |
| Audience contains `KEYCLOAK_AUDIENCE` | `audience=`, supplied by the audience mapper on the `frontend` client | 401 |
| Not expired | PyJWT checks `exp` **if present** | 401 |

It returns the decoded claims as a `dict`. Handlers that need the caller declare `claims: dict = Depends(current_user)` (see `/me`).
`require_login` (`[Depends(current_user)]`) runs the same check but throws the claims away. Use it when "is signed in" is all that matters.

**Key handling:** `PyJWKClient` caches the key set (default 5 min) and fetches it again when a token has an unknown `kid`, **at most once per 30 s** (PyJWT's `cooldown_duration`). Keycloak key rotation therefore works without a restart, but a token signed with a key rotated in the last 30 s can be rejected once. The first request after startup, or after a rotation, pays one HTTP round trip to Keycloak.

### 3.3 Configuration

Environment variables, with `.env` loaded by `python-dotenv` at import time. They're read into a plain `settings` dict in [dependencies.py](../app/dependencies.py).

| Variable | Default | Must match |
|---|---|---|
| `KEYCLOAK_ISSUER` | `http://localhost:8081/realms/jwt-lab` | the `iss` Keycloak puts in tokens, driven by `KC_HOSTNAME` in `docker-compose.yml`. The browser and the API both reach Keycloak at `localhost:8081`, so it matches without any hosts-file entry |
| `KEYCLOAK_AUDIENCE` | `fastapi-server` | `included.custom.audience` of the audience mapper in `../../keycloak/jwt-lab-realm.json` |
| `CORS_ORIGIN` | `http://localhost:5174` | the SPA origin, also registered as the Keycloak client's web origin |
| `APP_NAME` | `fastapi-server` | n/a |
| `DATABASE_URL` | `postgresql+psycopg://app:app@localhost:5435/app` | the Postgres reachable **from where FastAPI runs** (the host). Password = `APP_DB_PASSWORD` in `../../.env`. Add `?sslmode=require` for AWS RDS |

The JWKS URL is **derived from the issuer**, so there's one fewer setting to get out of sync.

The **Compose side** has its own `../../.env` (template: `../../.env.example`): `COMPOSE_PROFILES`, the Postgres admin password, the two database role passwords and `KC_DB_URL`. That's Keycloak's JDBC URL as seen **from inside Docker**, so it says `db:5432` while FastAPI's URL says `localhost:5435`. Both `.env` files are gitignored; the `.env.example` files are committed.

## 4. Deployment topology (lab)

This is how it runs **today**, on one Windows machine, next to the sibling Kerberos project (different ports and realm name, so both can run at once). The production target is in [deployment.md](deployment.md).

```mermaid
flowchart LR
    subgraph host[Windows host]
        br[Any browser]
        api[FastAPI :8001<br/>.venv, fastapi dev]
        vite[Vite :5174]
    end
    subgraph docker[Docker network 'lab' — compose project keycloak-jwt-python]
        kc[keycloak :8081→8080<br/>dev mode, KC_DB=postgres]
        db[(db: postgres:17<br/>:5435→5432, volume pg-data<br/>profile local-db)]
    end
    kc -- "db:5432 / keycloak" --> db
    br --> vite
    br --> kc
    api -- JWKS --> kc
    api -- "localhost:5435 / app" --> db
```

Swap the `db` box for an installed Postgres or AWS RDS by configuration only (D12). Then Keycloak connects via `host.docker.internal` or the RDS endpoint, and FastAPI via `localhost:5432` or the endpoint.

| | This project | Sibling `keykloak-python` |
|---|---|---|
| Keycloak / realm | `localhost:8081` / `jwt-lab` | `keycloak.lab.local:8080` / `lab` |
| API / frontend / Postgres | 8001 / 5174 / 5435 | 8000 / 5173 / 5434 |
| Extra containers | none | KDC, `keycloak-init` |

The realm names differ on purpose. Browsers don't separate cookies by port, so two Keycloaks on `localhost` with the same realm path would overwrite each other's session cookies.

- **The realm comes entirely from the import** ([keycloak/jwt-lab-realm.json](../../keycloak/jwt-lab-realm.json)): client `frontend` with PKCE and the audience mapper, self-registration, login by username or email, unique emails, and a seeded demo user `alice` / `alice123`. No post-import script is needed. Keycloak requires the file name to be `<realm>-realm.json`.
- **First start of the `db` container** runs [postgres/create-databases.sql](../../postgres/create-databases.sql) (via `postgres/initdb.sh`): roles `app` and `keycloak`, one database each, cross-database CONNECT revoked. For an installed Postgres or RDS, run the same file once: `psql -h <host> -U <admin> -d postgres -v app_password=… -v keycloak_password=… -f postgres/create-databases.sql` (the two `-v` passwords are required). It's safe to re-run.
- **Everything persists in Postgres** (volume `pg-data`): Keycloak accounts, sessions and the realm, and the app's users and profiles. So the realm import runs **only on first start**. Later edits to `jwt-lab-realm.json` need `docker compose down -v` (which wipes the database) or a change in the admin console.
- **App tables come from Alembic**, not from the container: `alembic upgrade head` (setup script step 3).
- The whole setup is scripted, needs **no admin rights**, and is safe to re-run: [scripts/setup-local-dev.ps1](../scripts/setup-local-dev.ps1).

## 5. Key decisions

| # | Decision | Why | Cost, and when to revisit |
|---|---|---|---|
| D1 | **The API validates JWTs; credentials end at Keycloak** | The API never handles passwords, sessions or login UX. Swapping or adding login methods (MFA, social, LDAP, Kerberos) is Keycloak config only | Needs Keycloak running. For a tiny app with one user table, an API that issues its own JWTs is simpler, but you then own password storage, reset and lockout |
| D2 | **Check tokens locally (JWKS), not by asking Keycloak (token introspection)** | No call to Keycloak per request, and the API keeps working if Keycloak is briefly down while keys are cached | **A token stays valid until `exp` even after logout or user disable.** Keep access tokens short (Keycloak default 5 min). Use introspection for high-risk endpoints if you need instant revocation |
| D3 | **Public SPA client + PKCE (S256)** | A browser can't keep a client secret; PKCE protects the code exchange | Tokens live in browser memory (keycloak-js). The upgrade is a backend-for-frontend (BFF) with HttpOnly session cookies, if XSS risk justifies it |
| D4 | **Audience mapper (`aud: fastapi-server`)** | Stops tokens issued for *other* clients in the realm from being replayed against this API | Every new API needs its own audience mapper |
| D5 | **Public reads, `require_login` per write endpoint** | Website-style: anyone can browse, members change data. Explicit in each decorator, so a reader sees which endpoint is protected | Opt-in is easy to forget. Mitigated by the 401 test on every write endpoint. When most endpoints are protected, flip to two routers (public, protected) mounted with/without the dependency |
| D6 | **PostgreSQL + SQLAlchemy 2.0 (sync) + psycopg 3 + Alembic** | Durable, transactional, enforces uniqueness and foreign keys. Works with several API instances. The standard managed option everywhere (RDS, Cloud SQL, Azure). Sync SQLAlchemy matches the sync endpoints (D7) | Needs a running database, even for local dev. Schema changes need a migration. Tests use SQLite for speed, so Postgres-only behaviour is covered by the live checks, not by `pytest` |
| D7 | **Sync (`def`) endpoints** | Simple; FastAPI runs them in a thread pool. JWKS fetch and SQL through psycopg are blocking anyway | Switch to `async def` together with an async DB driver, not before |
| D8 | **Settings as a dict, not `pydantic-settings`** | Five values, no extra dependency | Move when settings need types, validation or nesting. Today a typo in `.env` silently falls back to the default |
| D9 | **Login and registration are Keycloak pages** (`keycloak.login()` / `keycloak.register()`), **login by username or email** | No credential-handling code in the app; password policy, brute-force protection, reset and email verification are Keycloak settings. Email login works here because no Kerberos provider sits in front (in the sibling project it had to be disabled) | The pages look like Keycloak, not like the app. Use a Keycloak theme to restyle them. A custom in-app login form (password grant) is deliberately avoided: OAuth 2.1 drops that grant |
| D10 | **Realm fully defined by the import file, seeded demo user** | One declarative file is the whole identity setup; no post-import script. `alice` makes the lab usable without registering first | Import runs only on first start (D12 persistence), so later edits to the file need `down -v` or the admin console. Never seed users with known passwords outside a lab |
| D11 | **SPA uses `check-sso` with a redirect, session-check iframe off** | Guests aren't forced to log in, and a returning user's Keycloak session is picked up on load. The iframe would work here (`localhost:8081` and `localhost:5174` are the same site), but in production Keycloak has its own domain and browsers block its third-party cookies | One extra redirect to Keycloak on each full page load. The SPA doesn't notice a logout done in another tab until reload |
| D12 | **Database location by configuration only** (Docker container by default, installed Postgres or AWS RDS by changing `.env`) | Same code and migrations in every environment. The Docker default needs nothing installed; RDS is what production would use | Two URLs to keep in sync (Keycloak's from inside Docker, FastAPI's from the host). External databases need a one-time `psql … -v app_password=… -v keycloak_password=… -f postgres/create-databases.sql` (§4). Only Docker mode was tested end to end |
| D13 | **One server, two databases, one owner role each; no superuser for the apps** | Least privilege: a bug or injection in the API can't read Keycloak's password hashes, and vice versa | Slightly more setup than one shared user. Keycloak and the app share the server's capacity and backups; split onto separate servers when their load or lifecycle diverges |

## 6. Known gaps and risks

Ordered by impact. None of these matter for the lab, but each needs fixing before real use.

1. **Authentication without authorization.** Any signed-in account, including one registered a minute ago, can update and **delete any** user or profile. Roles (`realm_access.roles`) and the caller's `sub` are available in the claims but unused. *Fix:* a `require_role("...")` dependency, plus ownership checks that compare `claims["sub"]` with the resource owner.
2. **App users aren't linked to identities.** `User` is a free-form record unrelated to the Keycloak account that made it (see [datamodel.md §4](datamodel.md#4-identity-vs-application-data)). *Fix:* store `sub` as the owner/subject key.
3. **Public reads expose every email address.** `GET /users/` returns all users with their emails to anonymous callers, and there's no paging or rate limit. *Fix:* a public read model without `email` (e.g. `UserPublic`), with full details only for signed-in users or owners.
4. **`exp` isn't required.** PyJWT checks `exp` only if it's there. A correctly signed token without `exp` would be accepted forever. Keycloak always sets it, but a defensive verifier should enforce it: `options={"require": ["exp", "iss", "aud"]}`. Also `leeway=0` means a small clock difference between Keycloak and the API can reject fresh tokens; set about 30 s.
5. **Error detail leaks verifier internals.** The 401 body includes PyJWT's message (e.g. "Invalid token: Audience doesn't match"). Useful in a lab; in production, log it server-side and return a generic message.
6. **Database secrets in `.env` files.** Fine for a lab; in production use a secrets manager (AWS Secrets Manager or SSM Parameter Store, or Kubernetes secrets), rotate the passwords, and require TLS to the database (`sslmode=verify-full` with the RDS CA bundle, not only `require`).
7. **Two dependency manifests.** `requirements.txt` is what's used. `pyproject.toml` (uv template, `name = "backend"`, `dependencies = []`) is out of sync. Pick one; with uv already on the machine, moving the deps into `pyproject.toml` and adding a lock file is the cleaner option. Nothing is version-pinned today.
8. **Lab-only settings:** plain HTTP, `sslRequired: none`, `admin/admin`, seeded `alice` / `alice123`, Keycloak in dev mode (`start-dev`; production needs `start` with TLS, on the same Postgres). Database passwords `app`/`keycloak`/`postgres`, no backups configured for `pg-data`. Self-registration has no email verification, CAPTCHA or brute-force settings tuned.
9. **No observability.** No structured logs, request IDs or metrics. `/health` is liveness only: it checks neither the database nor Keycloak's JWKS. Add a `/ready` that runs `SELECT 1` for load balancers and Kubernetes.

## 7. Testing strategy

| Level | What | Where |
|---|---|---|
| Unit / contract | Token verification: valid; missing; wrong `aud`, `iss`; expired; forged signature. **Public reads 200 and every write endpoint 401 without a token.** Uses a locally generated RSA key, with JWKS patched out, so no Keycloak is needed | [tests/test_auth.py](../tests/test_auth.py) |
| Service + router + schema | Full CRUD lifecycle: create, read, update, list by `user_id`, cascade delete (foreign key), 404s, duplicate username/email → 409 with rollback. Runs on a fresh **in-memory SQLite** per test (`tests/conftest.py`, foreign keys on), so no Docker is needed. Auth replaced with `dependency_overrides` | [tests/test_crud.py](../tests/test_crud.py) |
| Component (frontend) | `UserForm` (create, edit prefill, API error) and `SignInMenu` (guest menu calls `login`/`register`; signed-in shows Log out). The SignInMenu test mocks the keycloak module; UserForm needs no mock | `../../frontend/src/users/UserForm.test.tsx`, `../../frontend/src/auth/SignInMenu.test.tsx` |
| End-to-end (scripted, by hand) | curl against the live stack: password login by **username** and by **email**, wrong password rejected, registration → signed in → log in again; then CRUD, 409 and cascade with both tokens, and persistence across a FastAPI restart | not in the repo yet |

Not covered yet: the end-to-end scripts aren't in CI or the repo. They need Docker plus the lab stack. A `tests/e2e/` folder with a compose-driven runner is the natural next step.

## 8. Evolution path

In the order that delivers value:

1. Authorization (roles + ownership by `sub`), together with gaps 1 and 2, because they shape the data model.
2. A `/ready` probe, backups, and connection-pool sizing once there are several API instances.
3. Harden the verifier (gaps 4 and 5), with typed settings via `pydantic-settings`.
4. Production deployment, designed in **[deployment.md](deployment.md)**: Dockerfiles, configurable frontend URLs and a `/ready` probe first; then GitHub Actions CI/CD, AWS Secrets Manager via External Secrets Operator, Kubernetes manifests (Kustomize, Argo CD), RDS, and Keycloak in production mode with TLS.
5. Observability: structured logging with the caller's `sub`, plus a readiness probe that checks JWKS.
