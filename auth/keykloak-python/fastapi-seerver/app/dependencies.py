import os

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

settings = {
    "APP_NAME": os.getenv("APP_NAME", "fastapi-server"),
    "KEYCLOAK_ISSUER": os.getenv("KEYCLOAK_ISSUER", "http://keycloak.lab.local:8080/realms/lab"),
    "KEYCLOAK_AUDIENCE": os.getenv("KEYCLOAK_AUDIENCE", "fastapi-server"),
    "CORS_ORIGIN": os.getenv("CORS_ORIGIN", "http://localhost:5173"),
    "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5434/app"),
}

# Keycloak's public signing keys; PyJWKClient fetches lazily and caches them.
jwks_client = jwt.PyJWKClient(f"{settings['KEYCLOAK_ISSUER']}/protocol/openid-connect/certs")


def current_user(creds: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> dict:
    """Validate the Keycloak access token and return its claims. FastAPI never sees Kerberos."""
    try:
        key = jwks_client.get_signing_key_from_jwt(creds.credentials).key
        return jwt.decode(
            creds.credentials,
            key,
            algorithms=["RS256"],
            audience=settings["KEYCLOAK_AUDIENCE"],
            issuer=settings["KEYCLOAK_ISSUER"],
        )
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid token: {e}", headers={"WWW-Authenticate": "Bearer"})


# Put on endpoints that change data: `@router.post(..., dependencies=require_login)`. Reads stay public.
require_login = [Depends(current_user)]
