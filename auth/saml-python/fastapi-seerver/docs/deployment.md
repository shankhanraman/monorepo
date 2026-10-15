# Deployment notes

> **Status: lab only.** Everything runs in Docker on one machine: Keycloak (`:8083`), FastAPI SP (`:8006`),
> Postgres (`:5440`). See [architecture.md](architecture.md). This note lists what changes before real SAML.

## Before production

| Concern | Lab today | Production |
|---|---|---|
| Transport | plain HTTP | **HTTPS** everywhere; SAML over http is for labs only |
| IdP keys | Keycloak dev keys, descriptor over http | real IdP signing cert; pin it; rotate on schedule |
| SP metadata | fetched/served ad hoc | publish `/saml/metadata` and register it with the IdP formally |
| AuthnRequest signing | off | sign requests; consider **encrypted assertions** for sensitive attributes |
| Single Logout | not wired | implement `/saml/sls` so SP logout ends the IdP session too |
| Session | signed cookie | a server-side session store if you need revocation before expiry |
| Replay / clock | defaults | keep `strict: true`; ensure IdP and SP clocks are close (NTP) |
| Keycloak store | in-container H2 | external Postgres (as the other Keycloak labs do), production mode + TLS |

## The pattern transfers

The SP code doesn't change across IdPs — point `IDP_METADATA_URL` at Azure AD / Okta / Shibboleth and
`python3-saml` verifies their assertions the same way. The only moving parts are the IdP's entityID, SSO URL and
signing certificate, all of which come from its metadata. `app/dependencies.py` and the session logic are
IdP-agnostic.
