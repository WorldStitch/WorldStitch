"""Add vault AI key columns and update platform roles.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-28

Changes:
  - vaults.ai_api_key (TEXT nullable) — encrypted vault-level OpenAI key
  - vaults.ai_key_shared (BOOLEAN default false) — whether members may use
    the vault owner's key for AI features
  - users.system_role — backfills any rows with 'moderator' to 'mod' to
    match the updated platform role vocabulary
"""

from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0012"
down_revision: Union[str, None] = "0011"
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


def upgrade() -> None:
    conn = op.get_bind()

    # ── Vault AI key columns ──────────────────────────────────────────────────
    if not _column_exists(conn, "vaults", "ai_api_key"):
        conn.execute(text("ALTER TABLE vaults ADD COLUMN ai_api_key TEXT"))

    if not _column_exists(conn, "vaults", "ai_key_shared"):
        conn.execute(text("ALTER TABLE vaults ADD COLUMN ai_key_shared BOOLEAN NOT NULL DEFAULT 0"))

    # ── Backfill ai_key_shared into the JSON blob so Vault.model_validate_json stays in sync ──
    rows = conn.execute(text("SELECT id, data FROM vaults")).fetchall()
    for row in rows:
        vault_id, data_json = row[0], row[1]
        try:
            data = json.loads(data_json or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if "ai_key_shared" not in data:
            data["ai_key_shared"] = False
            conn.execute(
                text("UPDATE vaults SET data = :d WHERE id = :id"),
                {"d": json.dumps(data), "id": vault_id},
            )

    # ── Normalise 'moderator' → 'mod' in users.system_role ───────────────────
    if _column_exists(conn, "users", "system_role"):
        conn.execute(text("UPDATE users SET system_role = 'mod' WHERE system_role = 'moderator'"))
        # Also update any 'moderator' references inside the JSON data blob
        rows = conn.execute(text("SELECT id, data FROM users WHERE system_role = 'mod'")).fetchall()
        for row in rows:
            user_id, data_json = row[0], row[1]
            try:
                data = json.loads(data_json or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("system_role") == "moderator":
                data["system_role"] = "mod"
                conn.execute(
                    text("UPDATE users SET data = :d WHERE id = :id"),
                    {"d": json.dumps(data), "id": user_id},
                )


def downgrade() -> None:
    # SQLite does not support DROP COLUMN before 3.35 — safe no-op
    pass
