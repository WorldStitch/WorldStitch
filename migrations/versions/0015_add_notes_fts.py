"""Add PostgreSQL full-text search to notes.

Adds search_vector (tsvector) column, GIN index, and a BEFORE INSERT/UPDATE
trigger that keeps search_vector in sync with title, content, and tags.
Backfills existing rows. PostgreSQL only — no-op on SQLite.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(text("ALTER TABLE notes ADD COLUMN IF NOT EXISTS search_vector tsvector"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notes_search_vector ON notes USING GIN(search_vector)"))
    # CREATE OR REPLACE is idempotent — safe if _setup_postgres_fts() ran first
    conn.execute(
        text("""
        CREATE OR REPLACE FUNCTION notes_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english',
                COALESCE(NEW.title, '') || ' ' ||
                COALESCE(NEW.content, '') || ' ' ||
                COALESCE(NEW.tags, '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    )
    conn.execute(text("DROP TRIGGER IF EXISTS notes_search_vector_trigger ON notes"))
    conn.execute(
        text(
            "CREATE TRIGGER notes_search_vector_trigger "
            "BEFORE INSERT OR UPDATE ON notes "
            "FOR EACH ROW EXECUTE FUNCTION notes_search_vector_update()"
        )
    )
    conn.execute(
        text("""
        UPDATE notes
        SET search_vector = to_tsvector('english',
            COALESCE(title, '') || ' ' ||
            COALESCE(content, '') || ' ' ||
            COALESCE(tags, '')
        )
        WHERE search_vector IS NULL
    """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(text("DROP TRIGGER IF EXISTS notes_search_vector_trigger ON notes"))
    conn.execute(text("DROP FUNCTION IF EXISTS notes_search_vector_update"))
    conn.execute(text("DROP INDEX IF EXISTS ix_notes_search_vector"))
    conn.execute(text("ALTER TABLE notes DROP COLUMN IF EXISTS search_vector"))
