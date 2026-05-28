"""
migrations/runner.py — Programmatic Alembic runner for WorldStitch.

Wraps Alembic's Python API so that SQLiteBackend.__init__ can apply any
pending schema migrations on startup without requiring a CLI call.

Concept mapping
---------------
SchemaVersion          → Alembic's ``alembic_version`` table (auto-managed)
@migration(v0, v1)     → Alembic revision files in migrations/versions/
run_migrations(engine) → ``alembic upgrade head`` via the Python API

Fresh-database behaviour
------------------------
If create_all() has already built the tables (no alembic_version row exists),
run_migrations() stamps the database at "head" so that Alembic doesn't try to
re-create tables that are already present.  Subsequent startups apply only
migrations newer than the stamped revision.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_INI_PATH = Path(__file__).parent.parent / "alembic.ini"


def run_migrations(engine: "Engine") -> None:
    """Apply all pending Alembic migrations to *engine*.

    Call this from SQLiteBackend.__init__ after Base.metadata.create_all().
    """
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import text

    cfg = Config(str(_INI_PATH))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        current = ctx.get_current_revision()

    if current is None:
        # No alembic_version row — either a brand-new DB (create_all just ran)
        # or a legacy DB that predates Alembic.  Distinguish the two cases by
        # checking whether the users table already has the ``email`` column.
        #
        # • Fresh DB  → create_all() built the correct schema; stamp to head so
        #   Alembic doesn't try to re-apply DDL that is already in place.
        # • Legacy DB → schema is outdated (email column missing); stamp to the
        #   revision just before 0004 so that ``upgrade head`` applies only the
        #   fix migration and not the earlier DDL migrations (which would
        #   conflict with tables already created by create_all).
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
                has_email_col = any(row[1] == "email" for row in rows)
        except Exception:
            has_email_col = True  # Cannot inspect; treat as fresh and stamp.

        if has_email_col:
            # Fresh DB: create_all() built the 14 legacy tables (revisions
            # 0001-0004).  Stamp to 0004 so Alembic skips those DDL migrations,
            # then upgrade to head so migration 0005 runs and creates the new
            # 35 tables that create_all() does not know about.
            command.stamp(cfg, "0004")
            command.upgrade(cfg, "head")
        else:
            # Stamp to 0003 (the revision immediately before the fix migration)
            # then upgrade so only migration 0004 runs.
            command.stamp(cfg, "0003")
            command.upgrade(cfg, "head")
    else:
        command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# @migration decorator — thin adapter for hand-written migration callables
# ---------------------------------------------------------------------------
# This decorator lets you write inline Python migrations alongside the
# Alembic revision files.  It is NOT a replacement for Alembic; it is a
# convenience for very simple, non-DDL data migrations that don't need a
# downgrade path.
#
# Usage example (in a migrations/versions/ file or your own module):
#
#   from migrations.runner import migration
#
#   @migration(from_version="0001", to_version="0002")
#   def backfill_titles(session):
#       for row in session.execute(text("SELECT id, data FROM notes")).fetchall():
#           ...
#
# The decorator registers the function but does NOT run it automatically;
# you call it explicitly when needed.

_registry: dict[tuple[str, str], callable] = {}


def migration(from_version: str, to_version: str):
    """Register a data-migration callable for (from_version → to_version)."""

    def _decorator(fn):
        _registry[(from_version, to_version)] = fn
        fn._migration_from = from_version
        fn._migration_to = to_version
        return fn

    return _decorator
