# Data model

> What data this service owns, what it only reads, and the rules on it.
> Context: [architecture.md](architecture.md) · request paths: [dataflow.md](dataflow.md).

The service deals with two separate kinds of data:

- **Application data** it *owns*: `User` and `Profile`, tables in PostgreSQL database `app`.
- **Identity data** it only *reads*: claims in the Keycloak access token. There are two sources of truth:
  - the **Kerberos KDC**, for admin-created users like `alice`, which Keycloak copies over on first login;
  - **Keycloak's own database**, for users who sign up through *Register*.

The most important fact about the current model: **these two aren't linked** (see [§4](#4-identity-vs-application-data)).

## 1. Application entities

```mermaid
erDiagram
    USER ||--o{ PROFILE : "has (by user_id), ON DELETE CASCADE"
    USER {
        int id PK "identity column, never reused"
        string username "NOT NULL, UNIQUE"
        string email "NOT NULL, UNIQUE"
    }
    PROFILE {
        int id PK "identity column, never reused"
        int user_id FK "NOT NULL, indexed, references users.id"
        string bio "NOT NULL, default empty string"
    }
```

### 1.1 `User`: [models/users.py](../app/models/users.py)

| Field | Type | Set by | Rules |
|---|---|---|---|
| `id` | `int` | server (Postgres identity) | Increasing, **never reused** after a delete. Never sent by the client (it's in the URL for `PUT`/`DELETE`) |
| `username` | `str` | client | Required, **unique** (DB constraint → 409). No length limit |
| `email` | `EmailStr` | client | **Unique** (DB constraint → 409). Must look like a valid address (`email-validator`, no DNS check). **Reserved names like `.local`, `.test` and `.localhost` are rejected.** That's why `carol@lab.local` fails while Kerberos-derived emails such as `alice@lab.local` appear in tokens |

### 1.2 `Profile`: [models/profiles.py](../app/models/profiles.py)

| Field | Type | Set by | Rules |
|---|---|---|---|
| `id` | `int` | server (Postgres identity) | Increasing, never reused, its own sequence |
| `user_id` | `int` | client | Must point to an existing `User` **on create and on update**: the router pre-checks for a clear 404, and the foreign key guarantees it. An update can move a profile to another user |
| `bio` | `str` | client | Optional, defaults to `""`, no length limit |

Relationship: **one user, many profiles**. **Deleting a user deletes their profiles**, done by Postgres (`ON DELETE CASCADE`), not by app code. Nothing stops a second profile for the same user. If the intended design is one profile per user, that rule is missing (see [§5](#5-invariants-and-gaps)).

### 1.3 Operations

| | Users | Profiles | Auth |
|---|---|---|---|
| List | `GET /users/` | `GET /profiles/?user_id=` (filter optional) | public |
| Read | `GET /users/{id}` | `GET /profiles/{id}` | public |
| Create | `POST /users/` → 201, **409** on duplicate username/email | `POST /profiles/` → 201, 404 if user missing | login |
| Update | `PUT /users/{id}` (full replace), 409 on duplicate | `PUT /profiles/{id}` (full replace), 404 if profile or user missing | login |
| Delete | `DELETE /users/{id}` → 204, **cascades** | `DELETE /profiles/{id}` → 204 | login |

## 2. Schema pattern: separate input and output models

Each entity file in `app/models/` holds **one table class and two Pydantic classes**:

```
UserRow (SQLAlchemy table "users")        ← only services touch it
UserCreate (input)  ──inherits──►  User (output) = UserCreate + id, from_attributes=True
ProfileRow / ProfileCreate / Profile        (same pattern)
```

Services convert rows to the output model (`User.model_validate(row)`), so **ORM objects never leave the service layer**. Routers and the API contract don't change if the table gains internal columns.

- **`*Create`** is what the client may send, so a client **can't choose `id`**: extra fields are ignored (Pydantic's default `extra="ignore"`).
- **The `*` read model** is what the API returns and stores. Routers declare it as `response_model`, so output is filtered through the schema even if the stored object later gains internal fields.
- Inheritance keeps the two in sync. The trade-off: once read and write fields differ (e.g. `password` on create only, `created_at` on read only), switch to a shared `*Base` plus separate `*Create`/`*Read`/`*Update` classes rather than piling on overrides.

**Updates are full replacements** (`PUT`) that reuse the `*Create` model: the client sends every field. There's no `PATCH` and no `*Update` model with optional fields. Add them when a client needs to change one field without knowing the others.

The frontend copies these types by hand in `../../frontend/src/users/types.ts` and `../../frontend/src/profiles/types.ts` (`X`, `XCreate = Omit<X, "id">`). **That's a second copy of the contract.** Generate it from `/openapi.json` (e.g. `openapi-typescript`) once the API grows past a couple of models.

## 3. Storage

PostgreSQL database **`app`**, owned by role **`app`** ([db.py](../app/db.py), [services/users.py](../app/services/users.py), [services/profiles.py](../app/services/profiles.py)). The schema is defined by migrations in [migrations/versions/](../migrations/versions/).

| Property | Behaviour | Notes |
|---|---|---|
| Durability | Postgres (Docker volume `pg-data`, or your server/RDS) | Survives API restarts, `fastapi dev` reloads, container recreates. Verified: data written, FastAPI stopped and started, data still there |
| Scope | Shared by all API processes | Several workers or pods see the same data |
| Sessions | One SQLAlchemy `Session` per request (`get_db`); services `commit()` | A failed write (e.g. a unique violation) is rolled back when the session closes; the next request is unaffected |
| ID generation | `GENERATED BY DEFAULT AS IDENTITY` | Unique under concurrency, never reused, survives restarts |
| Uniqueness | `UNIQUE(username)`, `UNIQUE(email)` | Violation → `IntegrityError` → **409** (handler in `main.py`) |
| Referential integrity | `profiles.user_id REFERENCES users(id) ON DELETE CASCADE`, indexed | Router pre-checks give a clear 404; the FK catches races. The index makes `?user_id=` and the cascade fast |
| Listing | `ORDER BY id` | No paging yet; add `limit`/`offset` (or keyset) when lists grow |
| Update | load row → set fields → commit | Last write wins; no optimistic locking (`ETag`/version column) |
| Connections | `create_engine(..., pool_pre_ping=True)`, default pool (5 + 10 overflow) | Pre-ping drops dead connections after a DB restart or RDS idle timeout. Size the pool per instance against the server's `max_connections` |

The services expose a small, storage-neutral interface. Each function takes the request's `Session` first:
- **users:** `list_users`, `get_user`, `create_user`, `update_user`, `delete_user`;
- **profiles:** `list_profiles(user_id=None)`, `get_profile`, `create_profile`, `update_profile`, `delete_profile`.

"Not found" comes back as `None`/`False`, never an exception. Duplicates surface as `IntegrityError`, which `main.py` maps to 409.

**Tests** run the same services on a fresh **in-memory SQLite** database per test ([tests/conftest.py](../tests/conftest.py), with `PRAGMA foreign_keys=ON` so the cascade works). That keeps `pytest` fast and Docker-free. Postgres-specific behaviour (identity columns, real concurrency) is covered by the migration and the live checks.

## 4. Identity vs application data

What the API receives from Keycloak with every **authenticated** request (access token claims). Guests send no token. Values below come from real lab tokens: `alice` (Kerberos) and `dana4920` (registered).

| Claim | Kerberos user | Registered user | Used by the API | Origin |
|---|---|---|---|---|
| `iss` | `http://keycloak.lab.local:8080/realms/lab` | same | verified | Keycloak realm URL (`KC_HOSTNAME`) |
| `aud` | `["fastapi-server", "account"]` | same | verified (must contain `fastapi-server`) | audience mapper on client `frontend` |
| `exp` | about 5 min after issue | same | verified (if present) | realm access-token lifespan |
| `azp` | `frontend` | same | — | the client that requested the token |
| `sub` | Keycloak user UUID | Keycloak user UUID | **not used** | Keycloak user id (local copy for Kerberos users) |
| `preferred_username` | `alice` | `dana4920` | returned by `/me` | Kerberos: principal without realm. Registered: chosen at sign-up |
| `email` | `alice@lab.local` | `dana4920@example.com` | returned by `/me` | Kerberos: `<principal>@<realm in lower case>`. Registered: entered at sign-up |
| `realm_access.roles` | default roles | default roles | **not used** | Keycloak role mappings |

**The API can't tell the two kinds of account apart, and doesn't need to.** Both are just valid tokens from the same issuer.

Where identity data actually lives:

```mermaid
flowchart LR
    kdc["KDC principal<br/>alice@LAB.LOCAL<br/>(created by admin: kadmin)"] -- "first login:<br/>Keycloak imports the user" --> kcu["Postgres db 'keycloak'<br/>table user_entity<br/>alice: federation_link set, password checked by KDC<br/>dana: local, password hash in Keycloak"]
    signup["Register<br/>(Keycloak sign-up form)"] -- "creates local user" --> kcu
    kcu -- "each login" --> tok["Access token claims"]
    tok -- "each authenticated request" --> api["fastapi-seerver<br/>(reads claims; can't read db 'keycloak')"]
    api -. "no link" .- app["Postgres db 'app'<br/>tables users, profiles"]
```

Username rules across the two stores:
- Sign-up **refuses a username that exists in the KDC**. Keycloak asks the Kerberos provider, which checks the KDC ("Username already exists"; verified with `alice`).
- The reverse isn't checked. If an admin later runs `kadmin addprinc dana4920`, the KDC and Keycloak hold two unrelated `dana4920` accounts, and Keycloak keeps using its local one. Treat usernames as one shared namespace operationally.

**The gap:** `User` records are created from form input and have no reference to `sub`. Today:

- any signed-in account (alice, or someone who registered a minute ago) can create, edit or **delete** any `User` or `Profile`;
- nothing ties a record to the person who created it;
- if an account is deleted in Keycloak or the KDC, its app data stays and nobody owns it.

Both live in the same Postgres server but in **separate databases with separate roles**. The API's role can't even connect to Keycloak's database, so the link has to come from the token's `sub`, never from a cross-database join.

**Recommended model**, best added in the next migration while the tables are still small:

| Field | Purpose |
|---|---|
| `User.subject` (`str`, unique) | `claims["sub"]`. Stable identity key. Use `sub`, not `preferred_username`, because usernames can be renamed and `sub` can't |
| `User.username`, `User.email` | copied from claims on first request ("just-in-time provisioning"), not typed into a form. Or drop them and read them from the token |
| `Profile.user_id` + unique constraint | if one profile per user is intended |
| `owner` checks | compare `claims["sub"]` with the resource's `subject` in the service layer |

## 5. Invariants and gaps

| Rule | Enforced? | Where / gap |
|---|---|---|
| `email` is a valid address | ✅ | Pydantic `EmailStr` → 422 |
| Client can't set `id` | ✅ | `*Create` models have no `id` |
| `Profile.user_id` points to an existing user | ✅ | foreign key; router pre-check for a clear 404 |
| No profiles left for a deleted user | ✅ | `ON DELETE CASCADE` |
| `id` unique, never reused | ✅ | identity columns |
| `username` unique | ✅ | `UNIQUE` constraint → 409; tested in `tests/test_crud.py` |
| `email` unique | ✅ | `UNIQUE` constraint → 409 (case-sensitive: `A@x.com` ≠ `a@x.com`) |
| Only signed-in users change data | ✅ | `require_login` on every write; 401 asserted in `tests/test_auth.py` |
| Only the **owner** changes a record | ❌ | no ownership model (§4) |
| One profile per user | ❌ | none, if intended (`UNIQUE(user_id)`) |
| Field lengths limited | ❌ | `VARCHAR` without length, `str` without `max_length`. An unlimited `bio` lets a client store megabytes |
| App data tied to the identity that created it | ❌ | §4 |

## 6. Schema and migrations

The schema lives in [migrations/versions/](../migrations/versions/); `0001_create_users_and_profiles.py` is the current head. The resulting tables:

```sql
CREATE TABLE users (
    id       INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    email    VARCHAR NOT NULL UNIQUE
);
CREATE TABLE profiles (
    id      INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bio     VARCHAR NOT NULL DEFAULT ''
);
CREATE INDEX ix_profiles_user_id ON profiles (user_id);
```

Workflow for any change:

1. Edit the `*Row` class in `app/models/` (and the Pydantic schemas if the API changes).
2. `alembic revision --autogenerate -m "add subject to users"`, then **read the generated file**. Autogenerate misses renames (it sees drop + add) and needs hand-written data migrations.
3. `alembic upgrade head` locally. Commit the migration with the code.
4. Deploy: run `alembic upgrade head` **before** starting the new app version. For zero downtime, make changes backwards compatible (add a nullable column → backfill → make it NOT NULL in a later release).

Next migrations worth doing, from §4 and §5:
- `users.subject TEXT UNIQUE` (Keycloak `sub`), plus `created_at TIMESTAMPTZ DEFAULT now()` on both tables;
- length limits (`VARCHAR(…)` and matching `max_length` in Pydantic, so oversized input gets a 422, not a DB error);
- `UNIQUE(user_id)` on profiles if it's one per user;
- case-insensitive email uniqueness (`UNIQUE (lower(email))`).
