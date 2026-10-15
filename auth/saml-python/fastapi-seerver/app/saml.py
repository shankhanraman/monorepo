"""SAML plumbing: build the python3-saml settings from Keycloak's descriptor, adapt a FastAPI
request into the dict python3-saml expects, and sign/verify our own session cookie.

SP-initiated SSO:
  /saml/login  -> build AuthnRequest -> 302 to Keycloak
  Keycloak authenticates the user, signs a SAML assertion, auto-POSTs it to /saml/acs
  /saml/acs    -> python3-saml verifies the signature against the IdP cert, reads the NameID
               -> we issue a signed session cookie
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.request

from app.config import settings

# NOTE: onelogin/xmlsec are imported lazily (inside functions), not at module load, so that importing
# app.main for the host test suite does not require the native xmlsec library. They load only when a
# /saml/* route actually runs (in the Docker container, where xmlsec is installed).

_idp_cache: dict | None = None


def _idp_data() -> dict:
    """Fetch and cache the IdP (Keycloak) SAML endpoints + signing cert from its descriptor."""
    global _idp_cache
    if _idp_cache is None:
        from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
        xml = urllib.request.urlopen(settings["IDP_METADATA_URL"], timeout=10).read()
        _idp_cache = OneLogin_Saml2_IdPMetadataParser.parse(xml)["idp"]
    return _idp_cache


def saml_settings() -> dict:
    base = settings["SP_BASE_URL"]
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": settings["SP_ENTITY_ID"],
            "assertionConsumerService": {
                "url": f"{base}/saml/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": f"{base}/saml/sls",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:2.0:nameid-format:unspecified",
        },
        "idp": _idp_data(),
        "security": {
            "wantAssertionsSigned": True,     # Keycloak signs the assertion; we require it
            "authnRequestsSigned": False,     # the SP doesn't sign its requests in this lab
            "wantMessagesSigned": False,
            "wantNameId": True,
        },
    }


def prepare_request(host: str, path: str, query: dict, form: dict) -> dict:
    """Adapt FastAPI request fields into python3-saml's request dict.

    host comes from the Host header (browser-facing, e.g. localhost:8006) so the ACS 'Destination'
    check matches even though the container itself listens on :8000 behind a port-map.
    """
    return {
        "https": "off",
        "http_host": host,
        "script_name": path,
        "get_data": query,
        "post_data": form,
    }


# --- our own session cookie (issued only after SAML succeeds) ---

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def sign_session(subject: str) -> str:
    payload = _b64(json.dumps({"sub": subject, "exp": int(time.time()) + settings["SESSION_HOURS"] * 3600}).encode())
    sig = _b64(hmac.new(settings["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_session(value: str | None) -> str | None:
    """Return the subject from a valid cookie, or None if missing / tampered / expired."""
    if not value or "." not in value:
        return None
    payload, _, sig = value.partition(".")
    good = _b64(hmac.new(settings["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, good):
        return None
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return data["sub"] if data["exp"] > time.time() else None
