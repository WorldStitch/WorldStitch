"""Add denormalized columns to notes and users for efficient querying.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07

Columns added
-------------
  notes.created_at  — denormalised from the JSON blob; used for sort / index
  notes.is_deleted  — soft-delete flag; allows DB-level filtering
  notes.folder      — denormalised folder_id; allows DB-level folder filter
  users.email       — denormalised email; enables indexed lookup by email
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("folder", sa.String(200), nullable=True, server_default="")
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("email", sa.String(200), nullable=True, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("email")

    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_column("folder")
        batch_op.drop_column("is_deleted")
        batch_op.drop_column("created_at")
