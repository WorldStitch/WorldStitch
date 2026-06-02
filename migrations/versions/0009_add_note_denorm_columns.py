"""Add denormalized title, content, tags, campaign_id columns to notes table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-25

These columns exist in the NoteRecord SQLAlchemy ORM model but were never
added to the production database via migration, causing UndefinedColumn
errors when creating or fetching notes.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0009"
down_revision: Union[str, None] = "0008"
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
    if _column_exists(conn, "notes", "title"):
        # Columns already present (added by create_all()); nothing to do.
        return
    with op.batch_alter_table("notes") as batch_op:
        batch_op.add_column(sa.Column("title", sa.Text(), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("content", sa.Text(), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("tags", sa.Text(), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("campaign_id", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_column("campaign_id")
        batch_op.drop_column("tags")
        batch_op.drop_column("content")
        batch_op.drop_column("title")
