import os

from dotenv import load_dotenv

load_dotenv()

settings = {
    "APP_NAME": os.getenv("APP_NAME", "fastapi-server"),
    "CORS_ORIGIN": os.getenv("CORS_ORIGIN", "http://localhost:5178"),
    "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5439/app"),
}
