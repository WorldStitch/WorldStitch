"""Add waitlist_applications table for early access signups.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "waitlist_applications" in inspector.get_table_names():
        return

    op.create_table(
        "waitlist_applications",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("world_description", sa.Text, nullable=True),
        sa.Column("referral_source", sa.String(50), nullable=False, server_default="other"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_waitlist_applications_email",
        "waitlist_applications",
        ["email"],
        unique=True,
    )
    op.create_index(
        "ix_waitlist_applications_status",
        "waitlist_applications",
        ["status"],
    )
    op.create_index(
        "ix_waitlist_applications_created_at",
        "waitlist_applications",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_waitlist_applications_created_at", table_name="waitlist_applications")
    op.drop_index("ix_waitlist_applications_status", table_name="waitlist_applications")
    op.drop_index("ix_waitlist_applications_email", table_name="waitlist_applications")
    op.drop_table("waitlist_applications")
