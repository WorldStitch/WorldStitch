"""Initial schema — create all WorldStitch tables.

Revision ID: 0001
Revises: (none — this is the base migration)
Create Date: 2026-05-05

Tables created
--------------
  users           — user accounts (JSON blob)
  groups          — campaign groups (JSON blob)
  vaults          — note vaults (JSON blob + denormalised owner/members)
  folders         — vault folders (JSON blob)
  notes           — note metadata (JSON blob; content lives on disk)
  characters      — character sheets (JSON blob)
  maps            — maps (JSON blob)
  images          — image records (JSON blob)
  sounds          — sound records (JSON blob)
  sessions        — game sessions (JSON blob)
  starred         — single-row set of starred note IDs (JSON array)
  invite_codes    — registration invite codes (code column indexed for lookup)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# upgrade — create all tables
# ---------------------------------------------------------------------------
def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "groups",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "vaults",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("members_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "folders",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("vault_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("vault_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "maps",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "images",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "sounds",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )

    op.create_table(
        "starred",
        sa.Column("id", sa.String(1), primary_key=True, nullable=False, server_default="1"),
        sa.Column("data", sa.Text(), nullable=False, server_default="[]"),
    )

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"], unique=True)


# ---------------------------------------------------------------------------
# downgrade — drop all tables in reverse dependency order
# ---------------------------------------------------------------------------
def downgrade() -> None:
    op.drop_index("ix_invite_codes_code", table_name="invite_codes")
    op.drop_table("invite_codes")
    op.drop_table("starred")
    op.drop_table("sessions")
    op.drop_table("sounds")
    op.drop_table("images")
    op.drop_table("maps")
    op.drop_table("characters")
    op.drop_table("notes")
    op.drop_table("folders")
    op.drop_table("vaults")
    op.drop_table("groups")
    op.drop_table("users")
