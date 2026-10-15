# Getting started, step by step

Bring up the SAML lab. Everything runs in Docker. Prerequisite: Docker Desktop (running).

| Piece | Address | Runs in |
|---|---|---|
| Keycloak (SAML IdP) | http://localhost:8083 | Docker |
| FastAPI (SAML SP) | http://localhost:8006 | Docker |
| PostgreSQL | localhost:5440 | Docker |

## Step 1: Start everything

```bash
cp .env.example .env              # first time
docker compose up --build -d      # first build compiles xmlsec (~2-3 min)
docker compose ps                 # db, keycloak, server all up
```

Keycloak takes ~30–60 s on a cold start to import realm `saml-lab`. Watch it:

```bash
docker compose logs -f keycloak   # wait for "Listening on: http://0.0.0.0:8080" and the realm import
```

## Step 2: Check the IdP descriptor (the SP reads this)

```bash
curl -s http://localhost:8083/realms/saml-lab/protocol/saml/descriptor | head -c 400
```

It contains the IdP's SSO endpoint and signing certificate — exactly what the SP fetches to verify assertions.

## Step 3: Sign in (browser)

1. Open **http://localhost:8006/saml/login**.
2. Keycloak's page appears — sign in as **alice / alice123**.
3. You land back on the SP, now signed in. `GET http://localhost:8006/me` returns your NameID.

## Step 3 (alternative): Sign in via script

From the repo's `auth/` folder (host needs `pip install requests`):

```bash
python saml_login_test.py
```

Expected:

```
1. Guest write (no session)  -> 401
2. Guest read                -> 200
3. Driving SAML SSO as alice -> saml_session set
4. /me WITH session          -> 200  {"sub":"alice"}
5. Write WITH session        -> 201
```

## Step 4: Tests (in the container)

`python3-saml`/`xmlsec` live in the image, so run pytest there:

```bash
docker compose run --rm server python -m pytest -q
```

## Stopping / fresh start

| What | Command |
|---|---|
| Stop | `docker compose down` |
| Wipe data (and Keycloak's H2) | `docker compose down -v` |

## If a step fails

| Problem | Fix |
|---|---|
| `/saml/login` 500 or "could not fetch descriptor" | Keycloak not ready yet — wait for the realm import, then retry |
| ACS "invalid Destination" | the SP must see the browser host `localhost:8006`; don't change `SP_BASE_URL` without matching Keycloak's ACS URL |
| ACS "Signature validation failed" | the Keycloak client must sign assertions (`saml.assertion.signature=true` in the realm) — it does by default here |
| login form POST returns the page again | the driver strips the `Secure` flag on Keycloak's cookie; if you changed it, restore `c.secure = False` |
| write still 401 after login | the `saml_session` cookie didn't stick — check `/saml/acs` returned 302 with `Set-Cookie` |
