"""Add content_hash columns to notes/characters/maps for embedding de-duplication.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-19

Adds a content_hash (SHA-256 hex digest) column to each table that carries an
embedding vector.  The embedding pipeline compares this hash before calling
the OpenAI API — if the hash matches the last-embedded content, the API call
is skipped entirely.
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
    conn.execute(text("ALTER TABLE notes ADD COLUMN IF NOT EXISTS embedding_hash VARCHAR(64)"))
    conn.execute(text("ALTER TABLE characters ADD COLUMN IF NOT EXISTS embedding_hash VARCHAR(64)"))
    conn.execute(text("ALTER TABLE maps ADD COLUMN IF NOT EXISTS embedding_hash VARCHAR(64)"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("ALTER TABLE maps DROP COLUMN IF EXISTS embedding_hash"))
    conn.execute(text("ALTER TABLE characters DROP COLUMN IF EXISTS embedding_hash"))
    conn.execute(text("ALTER TABLE notes DROP COLUMN IF EXISTS embedding_hash"))
