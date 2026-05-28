"""Add indexes to notes and users tables.

Revision ID: 0003
Revises: 0002r
Create Date: 2026-05-07

Indexes added
-------------
  ix_notes_created_at  — range scans / sorting by creation time
  ix_notes_owner_id    — per-user note listing
  ix_notes_vault_id    — per-vault note listing
  ix_notes_is_deleted  — fast is_deleted filter
  ix_notes_folder      — per-folder note listing
  ix_users_email       — unique email lookup
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002r"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_notes_created_at", "notes", ["created_at"])
    op.create_index("ix_notes_owner_id", "notes", ["owner_id"])
    op.create_index("ix_notes_vault_id", "notes", ["vault_id"])
    op.create_index("ix_notes_is_deleted", "notes", ["is_deleted"])
    op.create_index("ix_notes_folder", "notes", ["folder"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_notes_folder", table_name="notes")
    op.drop_index("ix_notes_is_deleted", table_name="notes")
    op.drop_index("ix_notes_vault_id", table_name="notes")
    op.drop_index("ix_notes_owner_id", table_name="notes")
    op.drop_index("ix_notes_created_at", table_name="notes")
