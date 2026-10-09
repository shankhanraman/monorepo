# Architecture

> Scope: the `fastapi-seerver` service and the identity infrastructure it depends on (Kerberos KDC, Keycloak).
> Companion docs: [datamodel.md](datamodel.md) (what data exists), [dataflow.md](dataflow.md) (how requests move) and [deployment.md](deployment.md) (CI/CD, secrets, Kubernetes: target design).
> Status: **learning lab**. Settings marked *lab-only* below must change before anything real runs on this.

## 1. Purpose

A FastAPI resource server whose callers authenticate with **Kerberos**, without the API itself knowing anything about Kerberos.
Keycloak sits between them and turns a Kerberos login (SPNEGO) into a standard **OIDC access token (JWT)**.
The API only checks JWTs.

The main architectural idea: **authentication protocols end at the identity provider.**
Swapping Kerberos for LDAP passwords, a social login or an MFA rule changes Keycloak's configuration, not this codebase.

It behaves like a normal website:
- **Guests can read.** Users and profiles can be listed and viewed without logging in.
- **Changes need an account.** Create, update and delete require a login.
- **The SPA's Sign in menu** offers **Log in** and **Register**:
  - *Log in:* Kerberos users with a ticket get in without a password; everyone else uses the password form.
  - *Register:* Keycloak's sign-up form, creating a Keycloak password account.

## 2. System context

```mermaid
flowchart LR
    user([User on a workstation])
    browser[Browser<br/>React SPA :5173]
    kdc[(MIT Kerberos KDC<br/>realm LAB.LOCAL :88)]
    kc[Keycloak<br/>realm lab :8080]
    api[fastapi-seerver<br/>:8000]
    pg[(PostgreSQL<br/>db 'app' + db 'keycloak')]

    user -- "kinit (password once)" --> kdc
    api -- "SQL as role 'app'" --> pg
    kc -- "JDBC as role 'keycloak'" --> pg
    browser -- "SPNEGO: service ticket" --> kc
    kc -- "validates ticket with keytab<br/>(no network call)" -.- kdc
    browser -- "TGS request (MIT GSSAPI)" --> kdc
    kc -- "OIDC code + PKCE -> JWT" --> browser
    browser -- "Bearer JWT" --> api
    api -- "JWKS (public keys), cached" --> kc
```

| Component | Responsibility | Trusts |
|---|---|---|
| **KDC** (`../../kdc/`) | Source of truth for *Kerberos users* (created by an admin with `kadmin`) and their passwords. Issues TGTs and service tickets | nothing |
| **Keycloak** (`../../keycloak/`) | Turns a Kerberos identity into an OIDC token. Owns the login and sign-up UX, sessions, token lifetimes and the audience of each token. **Stores all accounts** (self-registered ones, plus copies of Kerberos users), sessions and realm settings in Postgres database `keycloak` | the KDC: the keytab for SPNEGO, plus direct KDC calls to check passwords and look up usernames |
| **PostgreSQL** (`../../postgres/`) | Two isolated databases: `app` (owned by role `app`) and `keycloak` (owned by role `keycloak`). Each role can only connect to its own database. A Docker container by default; an installed server or AWS RDS by configuration (D12) | n/a |
| **fastapi-seerver** | Business API: users and profiles, stored in database `app` | Keycloak only, by checking JWT signatures against Keycloak's published keys |
| **React SPA** (`../../frontend/`) | Gets tokens (keycloak-js, PKCE) and calls the API | nothing; it's a public client and holds no secrets |

Trust is **one-directional and narrow**. The API trusts exactly one issuer, one audience and one algorithm. It never talks to the KDC and has no keytab.

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
| `KEYCLOAK_ISSUER` | `http://keycloak.lab.local:8080/realms/lab` | the `iss` Keycloak puts in tokens. That's driven by `KC_HOSTNAME`, so browser and API must reach Keycloak by the **same hostname** |
| `KEYCLOAK_AUDIENCE` | `fastapi-server` | `included.custom.audience` of the audience mapper in `../../keycloak/lab-realm.json` |
| `CORS_ORIGIN` | `http://localhost:5173` | the SPA origin, also registered as the Keycloak client's web origin |
| `APP_NAME` | `fastapi-server` | n/a |
| `DATABASE_URL` | `postgresql+psycopg://app:app@localhost:5434/app` | the Postgres reachable **from where FastAPI runs** (the host). Password = `APP_DB_PASSWORD` in `../../.env`. Add `?sslmode=require` for AWS RDS |

The JWKS URL is **derived from the issuer**, so there's one fewer setting to get out of sync.

The **Compose side** has its own `../../.env` (template: `../../.env.example`): `COMPOSE_PROFILES`, the Postgres admin password, the two database role passwords and `KC_DB_URL`. That's Keycloak's JDBC URL as seen **from inside Docker**, so it says `db:5432` while FastAPI's URL says `localhost:5434`. Both `.env` files are gitignored; the `.env.example` files are committed.

## 4. Deployment topology (lab)

This is how it runs **today**, on one Windows machine. The production target (EKS, RDS, Secrets Manager, GitHub Actions) is in [deployment.md](deployment.md).

```mermaid
flowchart LR
    subgraph host[Windows host]
        ff[Firefox + MIT Kerberos<br/>krb5.ini -> 127.0.0.1:88]
        api[FastAPI :8000<br/>.venv, fastapi dev]
        vite[Vite :5173]
        hosts[/hosts: keycloak.lab.local, kdc.lab.local -> 127.0.0.1/]
    end
    subgraph docker[Docker network 'lab']
        kdc[kdc :88<br/>volume kdc-data]
        kc[keycloak :8080<br/>dev mode, KC_DB=postgres]
        init[keycloak-init<br/>one-shot kcadm]
        kt[(volume keytabs)]
        db[(db: postgres:17<br/>volume pg-data<br/>profile local-db)]
    end
    kdc -- writes --> kt
    kt -- read-only --> kc
    init -- admin API --> kc
    kc -- "db:5432 / keycloak" --> db
    ff --> kdc
    ff --> kc
    api -- JWKS --> kc
    api -- "localhost:5434 / app" --> db
```

Swap the `db` box for an installed Postgres or AWS RDS by configuration only (D12). Then Keycloak connects via `host.docker.internal` or the RDS endpoint, and FastAPI via `localhost:5432` or the endpoint.

- `keycloak-init` ([init.sh](../../keycloak/init.sh)) exists because a realm import can't set everything. It:
  - switches the browser flow's Kerberos step to ALTERNATIVE;
  - disables `VERIFY_PROFILE`;
  - enables self-registration with `loginWithEmailAllowed=false` (see D10) and `duplicateEmailsAllowed=false`.

  It's idempotent and runs on every `up`.
- **First start of the `db` container** runs [postgres/create-databases.sql](../../postgres/create-databases.sql) (via `postgres/initdb.sh`): roles `app` and `keycloak`, one database each, cross-database CONNECT revoked. For an installed Postgres or RDS, run the same file once: `psql -h <host> -U <admin> -d postgres -v app_password=… -v keycloak_password=… -f postgres/create-databases.sql` (the two `-v` passwords are required). It's safe to re-run.
- **Everything persists in Postgres** (volume `pg-data`): Keycloak accounts, sessions and the realm, and the app's users and profiles. So the realm import runs **only on first start**. Later edits to `lab-realm.json` need `docker compose down -v` (which wipes the database and the KDC) or a change in `init.sh`.
- **App tables come from Alembic**, not from the container: `alembic upgrade head` (setup script step 6).
- The whole setup is scripted and safe to re-run with [scripts/setup-local-dev.ps1](../scripts/setup-local-dev.ps1).

## 5. Key decisions

| # | Decision | Why | Cost, and when to revisit |
|---|---|---|---|
| D1 | **The API validates JWTs; Kerberos ends at Keycloak** | The API stays protocol-agnostic. No keytab, GSSAPI or SPN per service. Works for browsers and machine clients alike | Needs Keycloak. Revisit only if a service must accept raw SPNEGO (legacy clients with no OIDC) |
| D2 | **Check tokens locally (JWKS), not by asking Keycloak (token introspection)** | No call to Keycloak per request, and the API keeps working if Keycloak is briefly down while keys are cached | **A token stays valid until `exp` even after logout or user disable.** Keep access tokens short (Keycloak default 5 min). Use introspection for high-risk endpoints if you need instant revocation |
| D3 | **Public SPA client + PKCE (S256)** | A browser can't keep a client secret; PKCE protects the code exchange | Tokens live in browser memory (keycloak-js). The upgrade is a backend-for-frontend (BFF) with HttpOnly session cookies, if XSS risk justifies it |
| D4 | **Audience mapper (`aud: fastapi-server`)** | Stops tokens issued for *other* clients in the realm from being replayed against this API | Every new API needs its own audience mapper |
| D5 | **Public reads, `require_login` per write endpoint** | Website-style: anyone can browse, members change data. Explicit in each decorator, so a reader sees which endpoint is protected | Opt-in is easy to forget. Mitigated by the 401 test on every write endpoint. When most endpoints are protected, flip to two routers (public, protected) mounted with/without the dependency |
| D6 | **PostgreSQL + SQLAlchemy 2.0 (sync) + psycopg 3 + Alembic** | Durable, transactional, enforces uniqueness and foreign keys. Works with several API instances. The standard managed option everywhere (RDS, Cloud SQL, Azure). Sync SQLAlchemy matches the sync endpoints (D7) | Needs a running database, even for local dev. Schema changes need a migration. Tests use SQLite for speed, so Postgres-only behaviour is covered by the live checks, not by `pytest` |
| D7 | **Sync (`def`) endpoints** | Simple; FastAPI runs them in a thread pool. JWKS fetch and SQL through psycopg are blocking anyway | Switch to `async def` together with an async DB driver, not before |
| D8 | **Settings as a dict, not `pydantic-settings`** | Five values, no extra dependency | Move when settings need types, validation or nesting. Today a typo in `.env` silently falls back to the default |
| D9 | **Registration through Keycloak's sign-up form; accounts live in Keycloak** | Keycloak's Kerberos provider is **read-only**: it can check and import KDC users but can't create principals. Built-in sign-up needs no custom code and no secrets in the API | Registered users log in with a password, not with a Kerberos ticket. Two user stores (KDC for admin-created staff, Keycloak for self-registered). If every account must be a Kerberos principal, use a writable directory (FreeIPA/AD via LDAP federation), not an API that runs `kadmin` |
| D10 | **`loginWithEmailAllowed=false`** | With it on, sign-up also looks the email up as a *username*. The Kerberos provider reads `dana@example.com` as principal `dana@EXAMPLE.COM`, finds no KDC for that realm and throws "Kerberos unreachable", so **every registration failed**. Verified in Keycloak 26.4 and in the provider's source | Users log in with a username, not an email. Typing an email from another domain into the login form still triggers that lookup and shows an error page instead of "invalid credentials" |
| D11 | **SPA uses `check-sso` with a redirect, session-check iframe off** | Guests aren't forced to log in, and a returning user's Keycloak session is picked up on load. The iframe needs third-party cookies (`keycloak.lab.local` framed by `localhost`), which Firefox blocks | One extra redirect to Keycloak on each full page load. The SPA doesn't notice a logout done in another tab until reload |
| D12 | **Database location by configuration only** (Docker container by default, installed Postgres or AWS RDS by changing `.env`) | Same code and migrations in every environment. The Docker default needs nothing installed; RDS is what production would use | Two URLs to keep in sync (Keycloak's from inside Docker, FastAPI's from the host). External databases need a one-time `psql … -v app_password=… -v keycloak_password=… -f postgres/create-databases.sql` (§4). Only Docker mode was tested end to end |
| D13 | **One server, two databases, one owner role each; no superuser for the apps** | Least privilege: a bug or injection in the API can't read Keycloak's password hashes, and vice versa. Verified: role `app` gets "permission denied" connecting to database `keycloak` | Slightly more setup than one shared user. Keycloak and the app share the server's capacity and backups; split onto separate servers when their load or lifecycle diverges |

## 6. Known gaps and risks

Ordered by impact. None of these matter for the lab, but each needs fixing before real use.

1. **Authentication without authorization.** Any signed-in account, including one registered a minute ago, can update and **delete any** user or profile. Self-registration makes this much more serious than in the admin-only lab before. Roles (`realm_access.roles`) and the caller's `sub` are available in the claims but unused. *Fix:* a `require_role("...")` dependency, plus ownership checks that compare `claims["sub"]` with the resource owner.
2. **App users aren't linked to identities.** `User` is a free-form record unrelated to the Keycloak user who made it (see [datamodel.md §4](datamodel.md#4-identity-vs-application-data)). *Fix:* store `sub` as the owner/subject key.
3. **Public reads expose every email address.** `GET /users/` returns all users with their emails to anonymous callers, and there's no paging or rate limit. *Fix:* a public read model without `email` (e.g. `UserPublic`), with full details only for signed-in users or owners.
4. **`exp` isn't required.** PyJWT checks `exp` only if it's there. Verified: a correctly signed token without `exp` gets 200 and never expires. Keycloak always sets it, but a defensive verifier should enforce it: `options={"require": ["exp", "iss", "aud"]}`. Also `leeway=0` means a small clock difference between Keycloak and the API can reject fresh tokens; set about 30 s.
5. **Error detail leaks verifier internals.** The 401 body includes PyJWT's message (e.g. "Invalid token: Audience doesn't match"). Useful in a lab; in production, log it server-side and return a generic message.
6. **Database secrets in `.env` files.** Fine for a lab; in production use a secrets manager (AWS Secrets Manager or SSM Parameter Store, or Kubernetes secrets), rotate the passwords, and require TLS to the database (`sslmode=verify-full` with the RDS CA bundle, not only `require`).
7. **Two dependency manifests.** `requirements.txt` is what's used. `pyproject.toml` (uv template, `name = "backend"`, `dependencies = []`) is out of sync. Pick one; with uv already on the machine, moving the deps into `pyproject.toml` and adding a lock file is the cleaner option. Nothing is version-pinned today.
8. **Lab-only settings:** plain HTTP, `sslRequired: none`, `admin/admin`, `alice123`, KDC master password in the entrypoint, Keycloak in dev mode (`start-dev`; production needs `start` with TLS, on the same Postgres). Database passwords `app`/`keycloak`/`postgres`, no backups configured for `pg-data`. Self-registration has no email verification, CAPTCHA or rate limit.
9. **No observability.** No structured logs, request IDs or metrics. `/health` is liveness only: it checks neither the database nor Keycloak's JWKS. Add a `/ready` that runs `SELECT 1` for load balancers and Kubernetes.

## 7. Testing strategy

| Level | What | Where |
|---|---|---|
| Unit / contract | Token verification: valid; missing; wrong `aud`, `iss`; expired; forged signature. **Public reads 200 and every write endpoint 401 without a token.** Uses a locally generated RSA key, with JWKS patched out, so no Keycloak is needed | [tests/test_auth.py](../tests/test_auth.py) |
| Service + router + schema | Full CRUD lifecycle: create, read, update, list by `user_id`, cascade delete (foreign key), 404s, duplicate username/email → 409 with rollback. Runs on a fresh **in-memory SQLite** per test (`tests/conftest.py`, foreign keys on), so no Docker is needed. Auth replaced with `dependency_overrides` | [tests/test_crud.py](../tests/test_crud.py) |
| Migrations | `alembic upgrade head` → `downgrade base` → `upgrade head` against the Postgres container | round trip by hand; the setup script (step 6) runs only `upgrade head` |
| Component (frontend) | `UserForm` (create, edit prefill, API error) and `SignInMenu` (guest menu calls `login`/`register`; signed-in shows Log out). The SignInMenu test mocks the keycloak module; UserForm needs no mock | `../../frontend/src/users/UserForm.test.tsx`, `../../frontend/src/auth/SignInMenu.test.tsx` |
| End-to-end (scripted, by hand) | Containerised curl clients: `kinit` + SPNEGO → token; Keycloak sign-up form → token; password login (Kerberos user and registered user); duplicate Kerberos username refused; CRUD with both tokens; persistence after a Keycloak recreate | not in the repo yet |

Not covered yet: the end-to-end scripts aren't in CI or the repo. They need Docker plus the lab stack. A `tests/e2e/` folder with a compose-driven runner is the natural next step.

## 8. Evolution path

In the order that delivers value:

1. Authorization (roles + ownership by `sub`), together with gaps 1 and 2, because they shape the data model.
2. ~~Persistence~~: done (Postgres + SQLAlchemy + Alembic, D6). Next: a `/ready` probe, backups, and connection-pool sizing once there are several API instances.
3. Harden the verifier (gaps 4 and 5), with typed settings via `pydantic-settings`.
4. Production deployment, designed in **[deployment.md](deployment.md)**: Dockerfiles, configurable frontend URLs and a `/ready` probe first; then GitHub Actions CI/CD, AWS Secrets Manager via External Secrets Operator, Kubernetes manifests in `../../k8s-project/` (Kustomize, Argo CD), RDS, and Keycloak in production mode with TLS against the company's AD/FreeIPA.
5. Observability: structured logging with the caller's `sub`, plus a readiness probe that checks JWKS.
