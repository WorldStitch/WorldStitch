"""Add ai_conversations table for persistent per-vault chat history.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vault_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("user_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("title", sa.String(200), nullable=False, server_default="Untitled"),
        sa.Column("messages", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_ai_conversations_vault_id", "ai_conversations", ["vault_id"])
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"])
    op.create_index("ix_ai_conversations_updated_at", "ai_conversations", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_conversations_updated_at", table_name="ai_conversations")
    op.drop_index("ix_ai_conversations_user_id", table_name="ai_conversations")
    op.drop_index("ix_ai_conversations_vault_id", table_name="ai_conversations")
    op.drop_table("ai_conversations")
