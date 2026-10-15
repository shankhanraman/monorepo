from fastapi.testclient import TestClient

from app.main import app
from app.saml import sign_session

client = TestClient(app)

# These cover the session cookie the SP issues AFTER a SAML login succeeds. The SAML signature
# verification itself (python3-saml + the IdP cert) is exercised by the live e2e, which needs Keycloak.


def test_auth():
    assert client.get("/health").status_code == 200

    # Reads are public.
    assert client.get("/users/").status_code == 200
    assert client.get("/profiles/").status_code == 200

    user = {"username": "a", "email": "a@example.com"}
    # Writes need a valid session cookie.
    assert client.post("/users/", json=user).status_code == 401                    # no cookie
    client.cookies.set("saml_session", "tampered.signature")
    assert client.post("/users/", json=user).status_code == 401                    # bad signature
    client.cookies.clear()

    client.cookies.set("saml_session", sign_session("alice"))
    assert client.post("/users/", json=user).status_code == 201                    # valid session
    assert client.put("/users/1", json=user).status_code == 200
    me = client.get("/me")
    assert me.status_code == 200 and me.json()["sub"] == "alice"
    client.cookies.clear()

    assert client.get("/me").status_code == 401
    assert client.delete("/users/1").status_code == 401
