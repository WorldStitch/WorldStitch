"""Add pgvector extension and embedding columns to notes, characters, maps.

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # Enable pgvector extension
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Add embedding columns
    conn.execute(text("ALTER TABLE notes ADD COLUMN IF NOT EXISTS embedding vector(1536)"))
    conn.execute(text("ALTER TABLE characters ADD COLUMN IF NOT EXISTS embedding vector(1536)"))
    conn.execute(text("ALTER TABLE maps ADD COLUMN IF NOT EXISTS embedding vector(1536)"))

    # IVFFlat indexes for cosine similarity search.
    # lists=100 is a reasonable default; tune upward as the vault grows.
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS notes_embedding_idx "
            "ON notes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS characters_embedding_idx "
            "ON characters USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS maps_embedding_idx "
            "ON maps USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(text("DROP INDEX IF EXISTS maps_embedding_idx"))
    conn.execute(text("DROP INDEX IF EXISTS characters_embedding_idx"))
    conn.execute(text("DROP INDEX IF EXISTS notes_embedding_idx"))

    conn.execute(text("ALTER TABLE maps DROP COLUMN IF EXISTS embedding"))
    conn.execute(text("ALTER TABLE characters DROP COLUMN IF EXISTS embedding"))
    conn.execute(text("ALTER TABLE notes DROP COLUMN IF EXISTS embedding"))
