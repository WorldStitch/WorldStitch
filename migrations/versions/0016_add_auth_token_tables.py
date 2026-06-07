"""Add email_verified to users, email_verification_tokens and password_reset_tokens tables.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-06
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # Add email_verified column to users
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "email_verified" not in existing_cols:
        op.add_column(
            "users",
            sa.Column(
                "email_verified",
                sa.Boolean,
                nullable=False,
                server_default=sa.false(),
            ),
        )

    # email_verification_tokens
    if "email_verification_tokens" not in inspector.get_table_names():
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("token", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime, nullable=True),
        )
        op.create_index(
            "ix_email_verification_tokens_token",
            "email_verification_tokens",
            ["token"],
            unique=True,
        )
        op.create_index(
            "ix_email_verification_tokens_user_id",
            "email_verification_tokens",
            ["user_id"],
        )

    # password_reset_tokens
    if "password_reset_tokens" not in inspector.get_table_names():
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("token", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime, nullable=False),
            sa.Column("used", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime, nullable=True),
        )
        op.create_index(
            "ix_password_reset_tokens_token",
            "password_reset_tokens",
            ["token"],
            unique=True,
        )
        op.create_index(
            "ix_password_reset_tokens_user_id",
            "password_reset_tokens",
            ["user_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_token", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

    op.drop_column("users", "email_verified")
