# SAML 2.0 lab

The same users-and-profiles API as the other labs, secured with **SAML 2.0 single sign-on**. Keycloak is the
**Identity Provider (IdP)**; FastAPI is the **Service Provider (SP)**, using the `python3-saml` library. Reads
are public; writes require a signed SAML assertion to have been consumed (then a session cookie).

```
Browser → FastAPI SP :8006 /saml/login
        → 302 to Keycloak IdP :8083 (carries a SAML AuthnRequest)
        → sign in (alice / alice123)
        → Keycloak signs a SAML assertion, auto-POSTs it to the SP's /saml/acs
        → SP verifies the signature against the IdP cert, reads the NameID, sets an HttpOnly session cookie
        → writes now allowed
```

## The mechanism, one sentence

**The SP sends the user to the IdP; the IdP returns a digitally-signed XML assertion saying "this is alice"; the
SP verifies that signature against the IdP's certificate and then trusts the identity.**

## Why it runs in Docker

`python3-saml` verifies XML signatures with the native **xmlsec1** library, which is painful to install on a
Windows host. So the SP runs in a container (the `Dockerfile` apt-installs `libxmlsec1-dev`), alongside Keycloak
and Postgres. One `docker compose up` brings up everything.

## The teachable files

| File | What it shows |
|---|---|
| [`keycloak/saml-lab-realm.json`](keycloak/saml-lab-realm.json) | the IdP side: a SAML client, ACS URL, "sign assertions" on, demo user alice |
| [`app/saml.py`](fastapi-seerver/app/saml.py) | SP settings from the IdP descriptor, the request adapter, the session cookie |
| [`app/routers/saml.py`](fastapi-seerver/app/routers/saml.py) | `/saml/login` (AuthnRequest), `/saml/acs` (verify + session), `/saml/metadata` |
| [`app/dependencies.py`](fastapi-seerver/app/dependencies.py) | `current_user`: writes need the session cookie the ACS issued |

The real XML-signature verification is done by `python3-saml` inside `auth.process_response()`.

## Ports

| | this lab |
|---|---|
| Keycloak (SAML IdP) | 8083 |
| FastAPI (SAML SP) | 8006 |
| Postgres | 5440 |

## Setup

Needs Docker Desktop.

```powershell
powershell -ExecutionPolicy Bypass -File fastapi-seerver\scripts\setup-local-dev.ps1   # Windows
```
```bash
bash fastapi-seerver/scripts/setup-local-dev.sh                                         # macOS / Linux
```

Or by hand:

```bash
cp .env.example .env
docker compose up --build -d     # first build compiles xmlsec (~2-3 min); then db + keycloak + server
```

Keycloak needs ~30–60 s on a cold start to import realm `saml-lab`.

## Use it (browser)

1. Open **http://localhost:8006/saml/login**.
2. You're redirected to Keycloak — sign in as **alice / alice123**.
3. Keycloak posts a signed assertion back to the SP, which sets a session cookie and returns you to the app.
4. You can now `POST`/`PUT`/`DELETE`; `GET /me` shows your SAML NameID.

## Use it (script, no browser)

From the repo's `auth/` folder (needs `pip install requests`):

```bash
python saml_login_test.py
```

It performs the full SP-initiated SSO (login → signed assertion → ACS → session) and checks a write succeeds
with the session and 401s without it.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /saml/login` | build the AuthnRequest, redirect to Keycloak |
| `POST /saml/acs` | Assertion Consumer Service: verify the signed response, issue the session cookie |
| `GET /saml/metadata` | SP metadata XML (what you'd hand an IdP to register this SP) |
| `GET /me` | the signed-in NameID (401 for guests) |
| `GET /users/`, `/profiles/` | public reads; writes need the session |

## Tests

`onelogin`/`xmlsec` only exist in the container, so run pytest there:

```bash
docker compose run --rm server python -m pytest -q
```

The suite covers the session-cookie gate (valid / tampered / missing) and the CRUD lifecycle. The XML-signature
verification itself is exercised by the live SSO above.

## Security notes

- **Assertions must be signed** (`wantAssertionsSigned`), and the SP verifies the signature against the IdP's
  certificate fetched from its descriptor, so `python3-saml` rejects any assertion whose signature doesn't
  verify. (The happy path is verified live by `saml_login_test.py`; the rejection path is enforced by the
  library + `wantAssertionsSigned`, not separately demonstrated here.)
- The SP issues its **own session cookie** after SSO; the SAML assertion isn't replayed on every request.
- Lab shortcuts: plain HTTP, `sslRequired: none`, `admin/admin`, a seeded demo user, SP doesn't sign its
  AuthnRequests, no SP-side assertion encryption, no Single Logout wired through. Harden all of these for real use.
