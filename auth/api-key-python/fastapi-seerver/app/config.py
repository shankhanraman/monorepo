import os

from dotenv import load_dotenv

load_dotenv()

# Settings live here (not in dependencies.py) so dependencies.py can import get_db
# without a circular import: db.py -> config.py, dependencies.py -> db.py + config.py.
settings = {
    "APP_NAME": os.getenv("APP_NAME", "fastapi-server"),
    "CORS_ORIGIN": os.getenv("CORS_ORIGIN", "http://localhost:5177"),
    "DATABASE_URL": os.getenv("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5438/app"),
}
