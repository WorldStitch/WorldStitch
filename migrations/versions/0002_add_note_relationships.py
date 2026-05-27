"""Add note_relationships table.

Revision ID: 0002r
Revises: 0002
Create Date: 2026-05-06

Adds the note_relationships table that tracks [[wikilink]] references between
notes.  The table is keyed on (source_path, target_path) and is kept in sync
by SQLiteBackend._sync_mentions() every time a note is written.

Migration is idempotent: if create_all() already created the table on a fresh
database, the upgrade() check skips table creation.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002r"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "note_relationships" not in inspector.get_table_names():
        op.create_table(
            "note_relationships",
            sa.Column("source_path", sa.String(1024), primary_key=True, nullable=False),
            sa.Column("target_path", sa.String(1024), primary_key=True, nullable=False),
        )


def downgrade() -> None:
    op.drop_table("note_relationships")
