"""Fix users table: add normalized columns and migrate data from JSON blob.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-07

Problem
-------
Older databases were created before the users table had individual columns for
``email``, ``password_hash``, ``role``, and ``is_active``.  Those databases
only have ``id`` and ``data`` (a JSON blob), so any ORM query that references
``users.email`` fails with a missing column error.

Fix
---
1. Add each missing column with a safe ``ALTER TABLE … ADD COLUMN`` guarded by
   a column-existence check via information_schema.  The check makes this
   migration idempotent — safe to run against both old and new databases.
2. For every row whose ``email`` column is NULL after step 1, parse the ``data``
   JSON blob and copy ``email``, ``password_hash``, ``role``, and ``is_active``
   into the new columns.

Raw SQL is used throughout (no SQLAlchemy ORM) to avoid the chicken-and-egg
problem where the ORM itself requires the columns to already exist.
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _column_exists(conn, table: str, column: str) -> bool:
    """Return True if *column* already exists on *table* (PostgreSQL)."""
    result = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table AND column_name = :col"
        ),
        {"table": table, "col": column},
    )
    return result.fetchone() is not None


# ---------------------------------------------------------------------------
# upgrade / downgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Add missing columns (idempotent — skipped if already present)
    # ------------------------------------------------------------------
    if not _column_exists(conn, "users", "email"):
        conn.execute(text("ALTER TABLE users ADD COLUMN email TEXT"))

    if not _column_exists(conn, "users", "password_hash"):
        conn.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))

    if not _column_exists(conn, "users", "role"):
        conn.execute(text("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'viewer'"))

    if not _column_exists(conn, "users", "is_active"):
        conn.execute(text("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1"))

    # ------------------------------------------------------------------
    # 2. Migrate data from JSON blob for rows where email IS NULL
    # ------------------------------------------------------------------
    rows = conn.execute(text("SELECT id, data FROM users WHERE email IS NULL")).fetchall()

    for row in rows:
        user_id: str = row[0]
        data_json: str = row[1] or "{}"

        try:
            data: dict = json.loads(data_json)
        except (json.JSONDecodeError, TypeError):
            continue

        email: str = data.get("email") or ""
        password_hash: str = data.get("password_hash") or ""

        # ``roles`` is a list in the Pydantic model; fall back to scalar ``role``
        roles = data.get("roles") or []
        role: str = roles[0] if roles else (data.get("role") or "viewer")

        is_active: int = 1 if data.get("is_active", True) else 0

        conn.execute(
            text(
                "UPDATE users "
                "SET email = :email, "
                "    password_hash = :password_hash, "
                "    role = :role, "
                "    is_active = :is_active "
                "WHERE id = :id"
            ),
            {
                "email": email,
                "password_hash": password_hash,
                "role": role,
                "is_active": is_active,
                "id": user_id,
            },
        )


def downgrade() -> None:
    # Leave added columns in place on downgrade; the old code only reads
    # ``id`` and ``data``, so the extra columns are harmless.
    pass
