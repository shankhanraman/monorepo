# Data flow

> How a login and a request move through the system. Structure: [architecture.md](architecture.md).

## 1. SP-initiated SSO

```
GET /saml/login
  -> python3-saml builds a SAML AuthnRequest, deflates+base64s it into ?SAMLRequest=
  -> 302 to http://localhost:8083/realms/saml-lab/protocol/saml

(Keycloak) user signs in as alice
  -> Keycloak builds a SAML Response containing a SIGNED assertion (subject = alice)
  -> returns an HTML page that auto-POSTs SAMLResponse to http://localhost:8006/saml/acs

POST /saml/acs
  -> auth.process_response() verifies: signature vs IdP cert, NotBefore/NotOnOrAfter, Audience, Destination
  -> read NameID ("alice") -> Set-Cookie saml_session=<signed {sub,exp}> (HttpOnly) -> 302 to /
```

## 2. A protected write

```
POST /users/  Cookie: saml_session=...
  -> current_user: read_session() verifies the HMAC + expiry -> {"sub":"alice"} -> handler -> 201
```

Failure paths (all 401 before the handler):

| Situation | Where |
|---|---|
| No cookie | `current_user` -> 401 "Not signed in" |
| Tampered / expired cookie | `read_session` returns None -> 401 |
| (at ACS) bad signature / wrong audience / wrong destination | `process_response` errors -> 400 at `/saml/acs`, no cookie issued |

## 3. Why the assertion is trustworthy

Keycloak signs the assertion with the realm's SAML signing key. The SP fetches that key's **certificate** from
the IdP descriptor (`/realms/saml-lab/protocol/saml/descriptor`) and `python3-saml` checks the XML signature
against it. A forged or altered assertion fails the signature check, so ACS never issues a session.

## 4. The Destination check (the gotcha)

`process_response` compares the Response's `Destination` to the SP's computed current URL. The request adapter
sets `http_host` from the **Host header** (`localhost:8006`) and `https:"off"`, so the computed URL is
`http://localhost:8006/saml/acs` — matching what Keycloak signed — even though the container really listens on
`:8000` behind the port-map.
