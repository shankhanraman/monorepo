import os
import secrets

from dotenv import load_dotenv

load_dotenv()

settings = {
    "APP_NAME": os.getenv("APP_NAME", "fastapi-server"),
    # Keycloak realm. The token, logout and JWKS URLs are derived from it.
    "KEYCLOAK_ISSUER": os.getenv("KEYCLOAK_ISSUER", "http://localhost:8082/realms/bff-lab"),
    # This backend is the OAuth 2.0 client (confidential): it holds the client secret, the browser never does.
    "OIDC_CLIENT_ID": os.getenv("OIDC_CLIENT_ID", "bff"),
    "OIDC_CLIENT_SECRET": os.getenv("OIDC_CLIENT_SECRET", ""),
    # Public origin of the site (Vite, which proxies /api and /auth here). Used for the redirect URI.
    "APP_URL": os.getenv("APP_URL", "http://localhost:5175"),
    # Signs the short-lived login-transaction cookie. Must be the same on every instance;
    # ponytail: random per process when unset, fine for one dev server, set it in .env for anything else
    "SESSION_SECRET": os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32),
    "SESSION_TTL_HOURS": int(os.getenv("SESSION_TTL_HOURS", "8")),
    # true behind HTTPS; false for http://localhost (browsers drop Secure cookies on plain http).
    "COOKIE_SECURE": os.getenv("COOKIE_SECURE", "false").lower() == "true",
    "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5436/app"),
}


def oidc_url(endpoint: str) -> str:
    """Keycloak OIDC endpoint, e.g. oidc_url("token")."""
    return f"{settings['KEYCLOAK_ISSUER']}/protocol/openid-connect/{endpoint}"
