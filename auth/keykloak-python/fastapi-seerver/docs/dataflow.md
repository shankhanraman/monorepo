# Data flow

> How data and credentials move through the system, step by step, including failure paths.
> Structure: [architecture.md](architecture.md) · entities and claims: [datamodel.md](datamodel.md).

| Flow | When |
|---|---|
| [1. Page load: guest or returning user](#1-page-load-guest-or-returning-user) | every full page load |
| [2. Sign in → Log in](#2-sign-in--log-in-kerberos-or-password) | user picks *Log in* |
| [3. Sign in → Register](#3-sign-in--register) | user picks *Register* |
| [4. Request pipeline](#4-request-pipeline-public-and-protected) | every API call |
| [5. CRUD flows](#5-crud-flows) | create / update / delete, cascade |
| [6. Token refresh](#6-token-refresh) | before each signed-in API call |
| [7. Signing keys and rotation](#7-signing-keys-jwks-and-rotation) | first verification, unknown `kid` |
| [8. CORS preflight](#8-cors-preflight) | browser, before non-simple requests |
| [9. Logout and revocation](#9-logout-and-revocation) | user clicks *Log out* |
| [10. Error reference](#10-error-reference) | all |

## 1. Page load: guest or returning user

The SPA never forces a login. Before rendering, it asks Keycloak, without any UI, whether a session already exists:

```mermaid
sequenceDiagram
    autonumber
    participant SPA as React SPA :5173
    participant KC as Keycloak :8080

    SPA->>SPA: keycloak.init({onLoad: "check-sso", pkce S256, checkLoginIframe: false})
    SPA->>KC: redirect /auth?...&prompt=none
    alt Keycloak session cookie exists (signed in earlier)
        KC-->>SPA: 302 ?code=...  → token exchange → authenticated = true
    else no session
        KC-->>SPA: 302 ?error=login_required → authenticated = false (guest)
    end
    SPA->>SPA: render <App/>, guest or signed in
```

- `prompt=none` means Keycloak **never shows a page** here, not even SPNEGO. A guest with a Kerberos ticket is still a guest until they click *Log in*. Logging someone in silently just for having a ticket would surprise them on a public site.
- It's a **redirect**, not the hidden-iframe check. The iframe would load `keycloak.lab.local` inside `localhost`, Firefox blocks those third-party cookies, and the check would always say "logged out" (decision D11).
- Tokens stay in memory only, so every full reload repeats this round trip.

## 2. Sign in → Log in (Kerberos or password)

`SignInMenu` → **Log in** → `keycloak.login()`:

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FF as Firefox (MIT GSSAPI)
    participant SPA as React SPA
    participant KC as Keycloak
    participant KDC as KDC :88

    U->>SPA: Sign in → Log in
    SPA->>KC: redirect /auth?client_id=frontend&code_challenge=... (PKCE)
    KC-->>FF: 401 WWW-Authenticate: Negotiate<br/>+ auto-submitting "continue" form
    alt has Kerberos ticket (kinit) and Firefox trusts keycloak.lab.local
        FF->>KDC: TGS-REQ for HTTP/keycloak.lab.local (using TGT)
        KDC-->>FF: service ticket
        FF->>KC: Authorization: Negotiate <SPNEGO token>
        KC->>KC: decrypt with keytab → alice@LAB.LOCAL (no KDC call)
    else no ticket (no kinit, Chrome/Edge, registered user)
        FF->>KC: browser auto-submits "continue" → username/password form
        U->>KC: username + password
        alt Kerberos user (e.g. alice)
            KC->>KDC: AS-REQ with alice's password (Kerberos provider)
            KDC-->>KC: ok / Pre-authentication failed
        else registered user
            KC->>KC: check local password hash
        end
    end
    KC-->>SPA: 302 redirect_uri?code=...
    SPA->>KC: POST /token (code + code_verifier)
    KC-->>SPA: access_token (~5 min), refresh_token
```

- **SPNEGO (top branch):** Keycloak validates the ticket with its keytab alone. Only the browser talks to the KDC.
- **Password branch:** a Kerberos user's password is checked **by the KDC**, and Keycloak never stores it. A registered user's password is a hash in Keycloak's database. Both were verified against the live stack.
- **PKCE:** a stolen `code` is useless without the `code_verifier`, which never leaves the SPA.

## 3. Sign in → Register

`SignInMenu` → **Register** → `keycloak.register()` opens Keycloak's sign-up page (`/protocol/openid-connect/registrations`):

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant SPA as React SPA
    participant KC as Keycloak
    participant KP as Kerberos provider
    participant KDC as KDC

    U->>SPA: Sign in → Register
    SPA->>KC: redirect /registrations?client_id=frontend&code_challenge=...
    KC-->>U: sign-up form (username, email, first/last name, password ×2)
    U->>KC: submit
    KC->>KP: getUserByUsername(username): does it exist anywhere?
    KP->>KDC: probe principal username@LAB.LOCAL
    alt principal exists (e.g. "alice")
        KC-->>U: "Username already exists"
    else free
        KC->>KC: create LOCAL user (password hash), log them in
        KC-->>SPA: 302 ?code=... → token exchange → signed in
    end
```

- The account is created **in Keycloak, not in the KDC**. The Kerberos provider is read-only (decision D9). The new user signs in with a password from then on, and the API sees an ordinary token ([datamodel.md §4](datamodel.md#4-identity-vs-application-data)).
- **`loginWithEmailAllowed` must be `false`.** Otherwise step 5 also runs with the *email* as the username. The provider turns `dana@example.com` into principal `dana@EXAMPLE.COM`, finds no KDC for that realm, and the sign-up fails with "Unexpected error" (Keycloak log: `Kerberos unreachable … Cannot locate KDC`). [keycloak/init.sh](../../keycloak/init.sh) enforces the setting (D10).
- Registered accounts are stored in Postgres (database `keycloak`, table `user_entity`) and survive Keycloak restarts and container recreates (verified).

## 4. Request pipeline: public and protected

```mermaid
flowchart TD
    A["SPA apiFetch(path)"] --> A2{"keycloak.authenticated?"}
    A2 -- "no (guest)" --> C0["fetch without Authorization"]
    A2 -- yes --> B["updateToken(30) (§6)"] --> C["fetch with Authorization: Bearer &lt;JWT&gt;"]
    C0 --> D["CORSMiddleware"]
    C --> D
    D --> E["Router match (path + method)"]
    E --> P{"endpoint has<br/>dependencies=require_login?"}
    P -- "no: GET list/read, /health" --> I
    P -- "yes: POST/PUT/DELETE, /me" --> F["HTTPBearer: header present?"]
    F -- no --> X1["401 Not authenticated"]
    F -- yes --> G["PyJWKClient: key for kid (§7)"] --> H["jwt.decode: RS256, iss, aud, exp"]
    H -- PyJWTError --> X2["401 Invalid token: &lt;reason&gt;"]
    H -- ok --> I["Validate path/query/body → *Create model"]
    I -- invalid --> X3["422 detail[]"]
    I -- ok --> J["Handler → service → Postgres<br/>(session from get_db, one per request)"]
    J --> K["201/200 + response_model JSON, or 204 empty"]
    K --> L["apiFetch: 204 → undefined, 2xx → json, else throw Error(detail)"]
```

Implementation details that matter:

- **Public endpoints ignore tokens.** A signed-in user's `GET /users/` carries a token, and the API doesn't look at it. A guest's request carries none and gets the same data.
- **Order of checks:** dependencies run first, and an `HTTPException` there stops the request before body validation errors are reported. A write with both a bad token and a bad body gets **401, not 422** (verified on FastAPI 0.143), so unauthenticated callers learn nothing about the schema.
- **Threading:** handlers and `current_user` are plain `def` and run in FastAPI's thread pool. The JWKS fetch and the SQL (psycopg) don't block the event loop. Each request gets its own DB session from the pool; Postgres identity columns and constraints keep concurrent writes consistent.
- **Claims:** `require_login` verifies the token but discards the claims. `/me` declares `Depends(current_user)` to get them.
- **Error text on the client:** [`apiFetch`](../../frontend/src/auth/apiFetch.ts) shows a string `detail` as-is and flattens a 422 list into `"<field>: <msg>, ..."`.

## 5. CRUD flows

All writes go through the same pattern in the UI: a form → `apiFetch` → the list is **fetched again** instead of patched locally, so the screen always shows server state.

**Create user** (`UserForm` in create mode → `Users.tsx`):

```mermaid
sequenceDiagram
    participant F as UserForm (create)
    participant U as Users.tsx
    participant API as routers/users.py
    participant S as services/users.py
    participant DB as Postgres (db "app")

    F->>F: browser checks required + type=email
    F->>U: onSubmit({username, email})
    U->>API: POST /users/ + Bearer
    API->>API: require_login → 401 · UserCreate validation → 422
    API->>S: create_user(db, data)
    S->>DB: INSERT INTO users … ; COMMIT
    alt username or email taken
        DB-->>S: unique violation (IntegrityError)
        S-->>API: raises → main.py handler → 409, session rolled back
        API-->>U: 409 "Already exists …" → shown under the form
    else ok
        DB-->>S: row with identity id
        API-->>U: 201 User
    end
    U->>U: reload GET /users/, call onChange() → App bumps version → Profiles reloads
    F->>F: clear inputs
```

**Update** (`Edit` → inline `UserForm`/`ProfileForm` prefilled → `PUT /{id}` with **all** fields):
- user: 404 if the id is gone, e.g. deleted in another tab;
- profile: 404 if the profile **or the new owner** is missing. The `<select>` only offers existing users, and the form submits exactly the owner it displays.

**Delete user, with cascade:**

```mermaid
sequenceDiagram
    participant U as Users.tsx
    participant API as routers/users.py
    participant SU as services/users.py
    participant DB as Postgres (db "app")
    participant App as App.tsx / Profiles.tsx

    U->>U: confirm("Delete X and all of their profiles?")
    U->>API: DELETE /users/{id} + Bearer
    API->>SU: delete_user(db, id)
    SU->>DB: DELETE FROM users WHERE id = … ; COMMIT
    DB->>DB: ON DELETE CASCADE removes that user's profiles (same transaction)
    API-->>U: 204 (no body)
    U->>App: onChange() → version+1
    App->>App: Profiles reloads GET /profiles/ + GET /users/ (owner names)
```

| Stage | Shape |
|---|---|
| Form state | `UserCreate` / `ProfileCreate` (TS) |
| Wire (request) | JSON body. `PUT` sends the full object |
| Validated | `*Create` (Pydantic). Email normalised by `email-validator` |
| Stored | row in `users`/`profiles` (`UserRow`/`ProfileRow`), id from the identity column |
| Returned by the service | `User`/`Profile` Pydantic model built from the row (`model_validate`) |
| Wire (response) | through `response_model`, or **204 with no body** for `DELETE` |

## 6. Token refresh

Only for signed-in users. Guests skip it (`apiFetch` checks `keycloak.authenticated`).

```mermaid
sequenceDiagram
    participant A as apiFetch
    participant KJ as keycloak-js
    participant KC as Keycloak

    A->>KJ: updateToken(30)
    alt token valid for > 30 s
        KJ-->>A: resolve (no network)
    else expires within 30 s
        KJ->>KC: POST /token grant_type=refresh_token
        KC-->>KJ: new access_token (+ refresh_token)
        KJ-->>A: resolve
    end
    A->>A: read keycloak.token (always the newest)
```

- No background timer; the refresh happens right before a call, so idle tabs don't talk to Keycloak.
- If the refresh token has also expired (SSO session ended), `updateToken` rejects and the call fails. After a reload, `check-sso` (§1) finds no session and the user is a **guest** again. They click *Log in*, which is silent with a Kerberos ticket.
- The 30 s margin covers network delay and small clock differences.

## 7. Signing keys (JWKS) and rotation

```mermaid
flowchart LR
    T["incoming JWT<br/>header.kid"] --> Q{"kid in cached<br/>JWKS? (cache ≤ 5 min)"}
    Q -- yes --> V[verify signature]
    Q -- "no / cache empty / expired" --> R["GET {issuer}/protocol/openid-connect/certs"]
    R --> Q2{kid found now?}
    Q2 -- yes --> V
    Q2 -- no --> E["401 Unable to find a signing key"]
    R -- "Keycloak unreachable" --> E2["401 (PyJWKClientConnectionError)"]
```

- **Startup does no network I/O.** `PyJWKClient` fetches only on the first verification. With Keycloak down, the API starts, `/health` is green, and **public reads keep working**. Only protected endpoints fail, with 401.
- **Rotation:** an unknown `kid` triggers one fetch of the key set, so no restart is needed. Garbage `kid`s also trigger that fetch; rate-limit it if the API is exposed publicly.
- **Keycloak outage:** cached keys keep existing tokens verifying for up to 5 min (decision D2).

## 8. CORS preflight

The SPA (`localhost:5173`) and the API (`localhost:8000`) are different origins. `apiFetch` always sends `Content-Type: application/json`, and signed-in calls also send `Authorization`, so the browser sends a preflight first, **even for a guest's `GET`**:

```
OPTIONS /users/   Origin: http://localhost:5173
                  Access-Control-Request-Method: POST
                  Access-Control-Request-Headers: authorization,content-type
→ 200 Access-Control-Allow-Origin: http://localhost:5173
```

`CORSMiddleware` answers before routing or auth, so a preflight never needs a token. Only `Authorization` and `Content-Type` are allowed. Add new custom headers to `allow_headers` in [main.py](../app/main.py).

## 9. Logout and revocation

```
SignInMenu "Log out" → keycloak.logout({redirectUri}) → Keycloak ends the SSO session → back to the SPA → check-sso → guest
```

- **The API isn't told.** An access token already issued stays valid **until `exp` (up to ~5 min)** because verification is local (D2). Use token introspection for endpoints that need instant revocation.
- Logout doesn't remove the **Kerberos TGT**. The next *Log in* is silent again. To really sign out on the workstation: `kdestroy`.

## 10. Error reference

| Status | Produced by | Body | Typical cause |
|---|---|---|---|
| 204 | `DELETE` routes | empty | success. `apiFetch` returns `undefined` |
| 401 | `HTTPBearer` | `{"detail": "Not authenticated"}` | write or `/me` without a token, e.g. a guest calling `POST` directly (older FastAPI versions return 403) |
| 401 | `current_user` | `{"detail": "Invalid token: <PyJWT message>"}` + `WWW-Authenticate: Bearer` | expired token, wrong `aud`/`iss`, bad signature, unknown `kid`, Keycloak unreachable for JWKS |
| 404 | routers | `{"detail": "User not found"}` / `"Profile not found"` | unknown id, deleted in the meantime, or a profile pointing to a missing user |
| 409 | `IntegrityError` handler (`main.py`) | `{"detail": "Already exists (username and email must be unique)"}` | duplicate username or email on create/update. The transaction is rolled back |
| 422 | Pydantic | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` | missing field, invalid email (including reserved names like `.local`), wrong types, non-integer path id |
| 500 | unhandled | plain text | database unreachable (wrong `DATABASE_URL`, container stopped, RDS security group): psycopg `OperationalError`. Check `alembic current` from `fastapi-seerver/` |

Keycloak-side errors, shown as Keycloak pages and never reaching the API:

| Symptom | Cause |
|---|---|
| Register → "Unexpected error when handling authentication request" | `loginWithEmailAllowed` was turned back on (§3). Check `docker compose logs keycloak \| grep "Cannot locate KDC"` |
| Register → "Username already exists" | the name exists in Keycloak **or as a Kerberos principal** |
| Log in with an email address → error page | typing an email from another domain triggers the same Kerberos lookup. Log in with the username |
| Log in never passwordless | no `kinit` ticket, Firefox prefs missing, or the user is a registered (non-Kerberos) account |

Debugging tips:

- **401 "Invalid issuer":** the token came through a different hostname than `KEYCLOAK_ISSUER`. Decode it, compare `iss`, and fix `KC_HOSTNAME` or the URL the SPA uses.
- **401 "Invalid audience":** the audience mapper is missing on the client that issued the token (`azp`).
- **401 right after login:** compare the clocks of the Keycloak container and the host. With zero leeway, a clock difference can make fresh tokens look invalid.
