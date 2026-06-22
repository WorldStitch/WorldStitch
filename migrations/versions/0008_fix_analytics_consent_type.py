"""Cast analytics_consent from INTEGER to BOOLEAN on PostgreSQL.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        # Drop the integer default first, then cast, then restore as boolean default
        conn.execute(text("ALTER TABLE users ALTER COLUMN analytics_consent DROP DEFAULT"))
        conn.execute(
            text("ALTER TABLE users ALTER COLUMN analytics_consent TYPE boolean USING analytics_consent::boolean")
        )
        conn.execute(text("ALTER TABLE users ALTER COLUMN analytics_consent SET DEFAULT false"))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        conn.execute(text("ALTER TABLE users ALTER COLUMN analytics_consent DROP DEFAULT"))
        conn.execute(
            text("ALTER TABLE users ALTER COLUMN analytics_consent TYPE integer USING analytics_consent::integer")
        )
        conn.execute(text("ALTER TABLE users ALTER COLUMN analytics_consent SET DEFAULT 0"))
