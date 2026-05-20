"""Add system_role column to users table and backfill from roles JSON.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-19

Users with "admin" in their roles list get system_role = "owner".
All other existing users default to "user" via the column default.
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "users", "system_role"):
        conn.execute(
            text("ALTER TABLE users ADD COLUMN system_role VARCHAR(20) NOT NULL DEFAULT 'user'")
        )

    # Backfill: users with "admin" in their roles JSON blob → system_role = "owner"
    rows = conn.execute(text("SELECT id, data FROM users")).fetchall()
    for row in rows:
        user_id, data_json = row[0], row[1]
        try:
            data = json.loads(data_json or "{}")
        except (json.JSONDecodeError, TypeError):
            continue

        roles = data.get("roles") or []
        if "admin" in roles:
            system_role = "owner"
            # Also update the JSON blob so the Pydantic model loads correctly
            data["system_role"] = system_role
            conn.execute(
                text("UPDATE users SET system_role = :sr, data = :d WHERE id = :id"),
                {"sr": system_role, "d": json.dumps(data), "id": user_id},
            )
        else:
            # Ensure the JSON blob has the field (Pydantic default handles new rows,
            # but update existing blobs so they're consistent)
            if "system_role" not in data:
                data["system_role"] = "user"
                conn.execute(
                    text("UPDATE users SET data = :d WHERE id = :id"),
                    {"d": json.dumps(data), "id": user_id},
                )


def downgrade() -> None:
    pass
