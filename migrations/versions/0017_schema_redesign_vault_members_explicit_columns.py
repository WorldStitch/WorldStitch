"""Schema redesign: vault_members table, explicit entity columns, fix note_relationships.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-08

What this migration does
------------------------
1. CREATE TABLE vault_members — normalised vault membership with vault-level roles.
   Replaces vaults.members_json blob.

2. DROP COLUMN vaults.members_json — superseded by vault_members.

3. ALTER TABLE characters — add explicit name/description/image_url/metadata columns,
   drop legacy data blob.

4. ALTER TABLE maps — add explicit name/description/image_url/map_url/metadata columns,
   drop legacy data blob.

5. ALTER TABLE groups — add explicit name/description/color/metadata columns,
   drop legacy data blob. owner_id already exists and is kept.

6. DROP + RECREATE note_relationships — old table used file paths as a composite PK
   (legacy desktop artifact). New table uses UUID PKs and FK references to notes.

No data migration — this is a clean-slate schema change for private beta.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table: str) -> bool:
    result = conn.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :t"),
        {"t": table},
    )
    return result.fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table AND column_name = :col"
        ),
        {"table": table, "col": column},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()

    # -------------------------------------------------------------------------
    # 1. vault_members — normalised vault membership table
    # -------------------------------------------------------------------------
    if not _table_exists(conn, "vault_members"):
        op.create_table(
            "vault_members",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column(
                "vault_id",
                sa.String(36),
                sa.ForeignKey("vaults.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("vault_role", sa.String(20), nullable=False),
            sa.Column(
                "joined_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "invited_by",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.UniqueConstraint("vault_id", "user_id", name="uq_vault_members_vault_user"),
        )
        op.create_index("ix_vault_members_vault_id", "vault_members", ["vault_id"])
        op.create_index("ix_vault_members_user_id", "vault_members", ["user_id"])

    # -------------------------------------------------------------------------
    # 2. Drop vaults.members_json — superseded by vault_members
    # -------------------------------------------------------------------------
    if _column_exists(conn, "vaults", "members_json"):
        with op.batch_alter_table("vaults") as batch_op:
            batch_op.drop_column("members_json")

    # -------------------------------------------------------------------------
    # 3. characters — add explicit columns, drop data blob
    # -------------------------------------------------------------------------
    if not _column_exists(conn, "characters", "name"):
        with op.batch_alter_table("characters") as batch_op:
            batch_op.add_column(sa.Column("name", sa.String(200), nullable=False, server_default=""))
            batch_op.add_column(sa.Column("description", sa.Text, nullable=True))
            batch_op.add_column(sa.Column("image_url", sa.String(1000), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "metadata",
                    sa.Text,
                    nullable=False,
                    server_default="{}",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
            batch_op.add_column(sa.Column("created_by", sa.String(36), nullable=True))

    if _column_exists(conn, "characters", "data"):
        with op.batch_alter_table("characters") as batch_op:
            batch_op.drop_column("data")

    # -------------------------------------------------------------------------
    # 4. maps — add explicit columns, drop data blob
    # -------------------------------------------------------------------------
    if not _column_exists(conn, "maps", "name"):
        with op.batch_alter_table("maps") as batch_op:
            batch_op.add_column(sa.Column("name", sa.String(200), nullable=False, server_default=""))
            batch_op.add_column(sa.Column("description", sa.Text, nullable=True))
            batch_op.add_column(sa.Column("image_url", sa.String(1000), nullable=True))
            batch_op.add_column(sa.Column("map_url", sa.String(1000), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "metadata",
                    sa.Text,
                    nullable=False,
                    server_default="{}",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
            batch_op.add_column(sa.Column("created_by", sa.String(36), nullable=True))

    if _column_exists(conn, "maps", "data"):
        with op.batch_alter_table("maps") as batch_op:
            batch_op.drop_column("data")

    # -------------------------------------------------------------------------
    # 5. groups — add explicit columns, drop data blob
    # -------------------------------------------------------------------------
    if not _column_exists(conn, "groups", "name"):
        with op.batch_alter_table("groups") as batch_op:
            batch_op.add_column(sa.Column("name", sa.String(200), nullable=False, server_default=""))
            batch_op.add_column(sa.Column("description", sa.Text, nullable=True))
            batch_op.add_column(sa.Column("color", sa.String(30), nullable=True))
            batch_op.add_column(
                sa.Column(
                    "metadata",
                    sa.Text,
                    nullable=False,
                    server_default="{}",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
            batch_op.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )

    if _column_exists(conn, "groups", "data"):
        with op.batch_alter_table("groups") as batch_op:
            batch_op.drop_column("data")

    # -------------------------------------------------------------------------
    # 6. note_relationships — drop path-based table and recreate with UUID PKs
    # -------------------------------------------------------------------------
    if _table_exists(conn, "note_relationships"):
        # Check if old schema (path-based) or new schema (id-based)
        has_id_col = _column_exists(conn, "note_relationships", "id")
        if not has_id_col:
            op.drop_table("note_relationships")

    if not _table_exists(conn, "note_relationships"):
        op.create_table(
            "note_relationships",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column(
                "vault_id",
                sa.String(36),
                sa.ForeignKey("vaults.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "source_note_id",
                sa.String(36),
                sa.ForeignKey("notes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "target_note_id",
                sa.String(36),
                sa.ForeignKey("notes.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("relationship_type", sa.String(200), nullable=False),
            sa.Column("label", sa.String(500), nullable=True),
            sa.Column(
                "metadata",
                sa.Text,
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("created_by", sa.String(36), nullable=True),
            sa.UniqueConstraint(
                "source_note_id",
                "target_note_id",
                "relationship_type",
                name="uq_note_rels_src_tgt_type",
            ),
        )
        op.create_index("ix_note_rels_vault_id", "note_relationships", ["vault_id"])
        op.create_index("ix_note_rels_source_note_id", "note_relationships", ["source_note_id"])
        op.create_index("ix_note_rels_target_note_id", "note_relationships", ["target_note_id"])


def downgrade() -> None:
    # Restore note_relationships to old path-based schema
    op.drop_table("note_relationships")
    op.create_table(
        "note_relationships",
        sa.Column("source_path", sa.String(1024), primary_key=True, nullable=False),
        sa.Column("target_path", sa.String(1024), primary_key=True, nullable=False),
    )

    # Restore groups.data and drop new columns
    with op.batch_alter_table("groups") as batch_op:
        batch_op.add_column(sa.Column("data", sa.Text, nullable=False, server_default="{}"))
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("metadata")
        batch_op.drop_column("color")
        batch_op.drop_column("description")
        batch_op.drop_column("name")

    # Restore maps.data and drop new columns
    with op.batch_alter_table("maps") as batch_op:
        batch_op.add_column(sa.Column("data", sa.Text, nullable=False, server_default="{}"))
        batch_op.drop_column("created_by")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("metadata")
        batch_op.drop_column("map_url")
        batch_op.drop_column("image_url")
        batch_op.drop_column("description")
        batch_op.drop_column("name")

    # Restore characters.data and drop new columns
    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(sa.Column("data", sa.Text, nullable=False, server_default="{}"))
        batch_op.drop_column("created_by")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
        batch_op.drop_column("metadata")
        batch_op.drop_column("image_url")
        batch_op.drop_column("description")
        batch_op.drop_column("name")

    # Restore vaults.members_json
    with op.batch_alter_table("vaults") as batch_op:
        batch_op.add_column(sa.Column("members_json", sa.Text, nullable=False, server_default="[]"))

    # Drop vault_members
    op.drop_index("ix_vault_members_user_id", table_name="vault_members")
    op.drop_index("ix_vault_members_vault_id", table_name="vault_members")
    op.drop_table("vault_members")
