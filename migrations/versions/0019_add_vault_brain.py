"""Add brain_content and brain_edit_role columns to vaults table.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE vaults ADD COLUMN IF NOT EXISTS brain_content TEXT"))
    conn.execute(
        text("ALTER TABLE vaults ADD COLUMN IF NOT EXISTS brain_edit_role VARCHAR(20) NOT NULL DEFAULT 'admin'")
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE vaults DROP COLUMN IF EXISTS brain_edit_role"))
    conn.execute(text("ALTER TABLE vaults DROP COLUMN IF EXISTS brain_content"))
