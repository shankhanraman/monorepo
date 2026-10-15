"""SAML SP endpoints: start SSO, consume the assertion, expose SP metadata."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import settings
from app.dependencies import SESSION_COOKIE
from app.saml import prepare_request, saml_settings, sign_session

router = APIRouter(prefix="/saml", tags=["saml"])


def _auth(req: dict):
    # Imported here (not at module load) so the host test suite can import app.main without xmlsec.
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    return OneLogin_Saml2_Auth(req, old_settings=saml_settings())


@router.get("/login")
def login(request: Request):
    """Build a SAML AuthnRequest and redirect the browser to Keycloak."""
    req = prepare_request(request.headers.get("host"), "/saml/login", dict(request.query_params), {})
    return RedirectResponse(_auth(req).login(), status_code=302)


@router.post("/acs")
async def acs(request: Request):
    """Assertion Consumer Service: verify the signed SAML Response, then issue our session cookie."""
    form = {k: v for k, v in (await request.form()).items()}
    req = prepare_request(request.headers.get("host"), "/saml/acs", {}, form)
    auth = _auth(req)
    auth.process_response()                      # verifies signature, conditions, audience, destination
    if auth.get_errors() or not auth.is_authenticated():
        raise HTTPException(400, f"SAML validation failed: {auth.get_errors()} {auth.get_last_error_reason()}")
    subject = auth.get_nameid()
    resp = RedirectResponse(settings["SP_BASE_URL"] + "/", status_code=302)
    resp.set_cookie(SESSION_COOKIE, sign_session(subject), httponly=True, samesite="lax",
                    max_age=settings["SESSION_HOURS"] * 3600, path="/")
    return resp


@router.get("/metadata")
def metadata():
    """SP metadata XML — what you'd hand an IdP to register this SP."""
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    s = OneLogin_Saml2_Settings(saml_settings(), sp_validation_only=True)
    return Response(s.get_sp_metadata(), media_type="application/xml")
