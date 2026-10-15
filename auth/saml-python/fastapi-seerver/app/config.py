import os

from dotenv import load_dotenv

load_dotenv()

settings = {
    "APP_NAME": os.getenv("APP_NAME", "fastapi-server"),
    "CORS_ORIGIN": os.getenv("CORS_ORIGIN", "http://localhost:8006"),
    "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5440/app"),

    # This SP's own identity and browser-facing base URL (what Keycloak redirects to and signs for).
    "SP_ENTITY_ID": os.getenv("SP_ENTITY_ID", "http://localhost:8006/saml/metadata"),
    "SP_BASE_URL": os.getenv("SP_BASE_URL", "http://localhost:8006"),

    # Where to fetch the IdP (Keycloak) SAML descriptor, as seen from INSIDE Docker. The endpoints
    # inside it are browser-facing because KC_HOSTNAME = http://localhost:8083.
    "IDP_METADATA_URL": os.getenv(
        "IDP_METADATA_URL", "http://keycloak:8080/realms/saml-lab/protocol/saml/descriptor"
    ),

    # Signs the session cookie we issue after a SAML login succeeds.
    "SESSION_SECRET": os.getenv("SESSION_SECRET", "saml-lab-dev-secret-change-me"),
    "SESSION_HOURS": int(os.getenv("SESSION_HOURS", "8")),
}
