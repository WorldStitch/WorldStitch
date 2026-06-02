"""Add vault_id and campaign_id columns to characters and maps tables.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-25

The CharacterRecord and MapRecord SQLAlchemy ORM models define vault_id and
campaign_id columns, but those columns were never added to the database via
migration.  New installs work because create_all() picks up the ORM definition,
but existing databases are missing the columns, causing OperationalError on any
write that populates these fields.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0010"
down_revision: Union[str, None] = "0009"
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

    if not _column_exists(conn, "characters", "vault_id"):
        with op.batch_alter_table("characters") as batch_op:
            batch_op.add_column(sa.Column("vault_id", sa.String(36), nullable=False, server_default=""))
            batch_op.add_column(sa.Column("campaign_id", sa.String(36), nullable=True))
            batch_op.create_index("ix_characters_vault_id", ["vault_id"])

    if not _column_exists(conn, "maps", "vault_id"):
        with op.batch_alter_table("maps") as batch_op:
            batch_op.add_column(sa.Column("vault_id", sa.String(36), nullable=False, server_default=""))
            batch_op.add_column(sa.Column("campaign_id", sa.String(36), nullable=True))
            batch_op.create_index("ix_maps_vault_id", ["vault_id"])


def downgrade() -> None:
    with op.batch_alter_table("maps") as batch_op:
        batch_op.drop_index("ix_maps_vault_id")
        batch_op.drop_column("campaign_id")
        batch_op.drop_column("vault_id")

    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_index("ix_characters_vault_id")
        batch_op.drop_column("campaign_id")
        batch_op.drop_column("vault_id")
