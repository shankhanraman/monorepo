"""Alembic environment: same database (DATABASE_URL in .env) and same table definitions as the app.

    alembic upgrade head                        # apply migrations (setup-local-dev.ps1 does this)
    alembic revision --autogenerate -m "..."    # after changing a *Row class in app/models/, then review the file
"""

from logging.config import fileConfig

from alembic import context

import app.models.profiles  # noqa: F401  (registers the tables on Base.metadata)
import app.models.users  # noqa: F401
from app.db import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it (e.g. for a DBA to review)."""
    context.configure(url=engine.url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
