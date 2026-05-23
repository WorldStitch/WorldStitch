"""
migrations/env.py — Alembic migration environment for WorldStitch.

How it works
------------
* Target metadata is pulled from the canonical 41-table schema defined in
  WorldStitch/storage/schema.py.  The legacy sqlite_backend.py ORM models
  are kept for the existing CRUD layer and will be retired in a follow-up PR.

* The database URL is resolved in this order:
    1. DATABASE_URL environment variable  (preferred for Docker / CI)
    2. sqlalchemy.url from alembic.ini    (fallback, defaults to sqlite:///worldstitch.db)

* Both online (real DB connection) and offline (SQL script output) modes are
  supported.

Common commands
---------------
    alembic upgrade head
    alembic downgrade -1
    alembic revision --autogenerate -m "add foo column"
    alembic history --verbose
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Pull in ORM metadata so autogenerate can diff against the live schema
# ---------------------------------------------------------------------------
# sys.path already includes the project root (prepend_sys_path = . in alembic.ini)
from WorldStitch.storage.schema import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to alembic.ini values
# ---------------------------------------------------------------------------
config = context.config

# Allow DATABASE_URL env var to override the ini file value
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ---------------------------------------------------------------------------
# Offline mode — emit raw SQL to stdout (useful for review / dry-run)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render as CREATE TABLE … IF NOT EXISTS so scripts are re-runnable
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect and apply migrations directly
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # batch mode required for SQLite ALTER TABLE support
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
