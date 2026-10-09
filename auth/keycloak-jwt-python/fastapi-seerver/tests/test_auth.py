import time
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.dependencies import settings
from app.main import app

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
client = TestClient(app)


def token(**overrides):
    claims = {
        "iss": settings["KEYCLOAK_ISSUER"],
        "aud": settings["KEYCLOAK_AUDIENCE"],
        "exp": int(time.time()) + 60,
        "preferred_username": "alice",
    } | overrides
    return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}


class FakeSigningKey:
    key = key.public_key()


# Stand in for Keycloak's JWKS endpoint so the test runs without Keycloak.
@patch("app.dependencies.jwks_client.get_signing_key_from_jwt", return_value=FakeSigningKey)
def test_auth(_):
    assert client.get("/health").status_code == 200
    assert client.get("/me", headers=token()).json()["username"] == "alice"

    # Reads are public; every write needs a valid token.
    assert client.get("/users/").status_code == 200
    assert client.get("/profiles/").status_code == 200
    user = {"username": "a", "email": "a@example.com"}
    assert client.post("/users/", json=user).status_code == 401
    assert client.put("/users/1", json=user).status_code == 401
    assert client.delete("/users/1").status_code == 401
    assert client.post("/profiles/", json={"user_id": 1}).status_code == 401
    assert client.put("/profiles/1", json={"user_id": 1}).status_code == 401
    assert client.delete("/profiles/1").status_code == 401
    assert client.post("/users/", json=user, headers=token(aud="other-app")).status_code == 401
    assert client.post("/users/", json=user, headers=token()).status_code == 201

    assert client.get("/me").status_code in (401, 403)  # no token
    assert client.get("/me", headers=token(aud="other-app")).status_code == 401
    assert client.get("/me", headers=token(iss="http://evil/realms/lab")).status_code == 401
    assert client.get("/me", headers=token(exp=int(time.time()) - 10)).status_code == 401

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode({"iss": settings["KEYCLOAK_ISSUER"], "aud": settings["KEYCLOAK_AUDIENCE"],
                         "exp": int(time.time()) + 60}, other_key, algorithm="RS256")
    assert client.get("/me", headers={"Authorization": "Bearer " + forged}).status_code == 401
