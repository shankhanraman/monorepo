"""create api_keys and seed two demo keys

Revision ID: 0002
Revises: 0001
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Demo keys, documented in .env.example. Plaintext only ever lives here; the table stores the hash.
DEMO_KEY = "mial_live_demo_do_not_use_in_prod"
REVOKED_KEY = "mial_live_revoked_example"


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def upgrade() -> None:
    api_keys = op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    # One active key (unlocks writes) and one inactive key (shows the revoked -> 401 path).
    op.bulk_insert(api_keys, [
        {"name": "demo", "prefix": DEMO_KEY[:9], "key_hash": _hash(DEMO_KEY), "active": True},
        {"name": "revoked-demo", "prefix": REVOKED_KEY[:9], "key_hash": _hash(REVOKED_KEY), "active": False},
    ])


def downgrade() -> None:
    op.drop_table("api_keys")
