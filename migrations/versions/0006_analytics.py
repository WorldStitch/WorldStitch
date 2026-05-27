"""Add analytics_events table and analytics_consent column on users.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    if conn.dialect.name == "postgresql":
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table AND column_name = :col"
            ),
            {"table": table, "col": column},
        )
        return result.fetchone() is not None
    else:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in rows)


def _table_exists(conn, table: str) -> bool:
    if conn.dialect.name == "postgresql":
        result = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        )
        return result.fetchone() is not None
    else:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchall()
        return bool(rows)


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "users", "analytics_consent"):
        conn.execute(
            text("ALTER TABLE users ADD COLUMN analytics_consent INTEGER NOT NULL DEFAULT 0")
        )

    if not _table_exists(conn, "analytics_events"):
        conn.execute(
            text("""
                CREATE TABLE analytics_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    created_at TIMESTAMP
                )
            """)
        )
        conn.execute(text("CREATE INDEX ix_analytics_events_user_id ON analytics_events (user_id)"))
        conn.execute(text("CREATE INDEX ix_analytics_events_event_type ON analytics_events (event_type)"))
        conn.execute(text("CREATE INDEX ix_analytics_events_created_at ON analytics_events (created_at)"))


def downgrade() -> None:
    pass
