"""
Async database engine and session factory for WorldStitch.

This is the single place the server connects to PostgreSQL. All route
handlers and services use AsyncSession via the shared session factory;
the only sync engine ever created is a short-lived one used at startup
to run Alembic migrations (Alembic has no async API).

DATABASE_URL is required — there is no SQLite fallback.
"""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set.\n"
            "WorldStitch requires a PostgreSQL database — there is no SQLite fallback.\n"
            "Example: DATABASE_URL=postgresql://user:pass@localhost:5432/worldstitch"
        )
    return url


def _async_url(url: str) -> str:
    """Normalise any postgres URL form to the asyncpg dialect."""
    url = re.sub(r"^postgres(ql)?(\+psycopg2)?://", "postgresql+asyncpg://", url)
    # asyncpg rejects libpq's sslmode query param — translate it.
    url = url.replace("?sslmode=require", "?ssl=true").replace("&sslmode=require", "&ssl=true")
    url = url.replace("?sslmode=disable", "").replace("&sslmode=disable", "")
    return url


def _sync_url(url: str) -> str:
    """Normalise any postgres URL form to the psycopg2 dialect (migrations only)."""
    return re.sub(r"^postgres(ql)?(\+asyncpg)?://", "postgresql+psycopg2://", url)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(_async_url(_database_url()), pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


def run_startup_migrations() -> None:
    """
    Create tables and apply pending Alembic migrations.

    Blocking by design — call from the lifespan via asyncio.to_thread().
    Uses a dedicated short-lived sync engine because Alembic is sync-only.
    """
    from server.orm import Base

    engine = create_engine(_sync_url(_database_url()), pool_pre_ping=True)
    try:
        Base.metadata.create_all(engine)

        try:
            from migrations.runner import run_migrations

            run_migrations(engine)
        except Exception as exc:
            logger.warning("Alembic migration run failed: %s", exc)

        try:
            _setup_postgres_fts(engine)
        except Exception as exc:
            logger.warning("Postgres FTS setup failed: %s — search falls back to LIKE.", exc)
    finally:
        engine.dispose()


def _setup_postgres_fts(engine) -> None:
    """Set up tsvector full-text search on notes (column, GIN index, trigger)."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE notes ADD COLUMN IF NOT EXISTS search_vector tsvector"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notes_search_vector ON notes USING GIN(search_vector)"))
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
            text("""
            CREATE TRIGGER notes_search_vector_trigger
            BEFORE INSERT OR UPDATE ON notes
            FOR EACH ROW EXECUTE FUNCTION notes_search_vector_update()
        """)
        )
        conn.execute(
            text("""
            UPDATE notes SET search_vector = to_tsvector('english',
                COALESCE(title, '') || ' ' ||
                COALESCE(content, '') || ' ' ||
                COALESCE(tags, '')
            ) WHERE search_vector IS NULL
        """)
        )
