"""Add vault_type column to vaults table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-25

Adds a vault_type column to distinguish the terminology used in the UI
(worldbuilding, tabletop, video_game, novel, film, custom).  Existing
rows default to 'worldbuilding', which preserves current behaviour.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    if conn.dialect.name == "postgresql":
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table AND column_name = :col"
            ),
            {"table": table, "col": column},
        )
        return result.fetchone() is not None
    else:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in rows)


def upgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "vaults", "vault_type"):
        # Column already present (added by create_all()); nothing to do.
        return
    with op.batch_alter_table("vaults") as batch_op:
        batch_op.add_column(
            sa.Column(
                "vault_type",
                sa.String(32),
                nullable=False,
                server_default="worldbuilding",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("vaults") as batch_op:
        batch_op.drop_column("vault_type")
