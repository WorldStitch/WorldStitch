"""
migrations/env.py — Alembic migration environment for WorldStitch.

How it works
------------
* Target metadata is pulled from the canonical 41-table schema defined in
  WorldStitch/storage/schema.py.

* DATABASE_URL environment variable is required — there is no SQLite fallback.
  Set it before running any alembic command:
    export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/worldstitch

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

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Pull in ORM metadata so autogenerate can diff against the live schema
# ---------------------------------------------------------------------------
# sys.path already includes the project root (prepend_sys_path = . in alembic.ini)
from server.orm import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to alembic.ini values
# ---------------------------------------------------------------------------
config = context.config

# DATABASE_URL is required — fail loudly if not set
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set.\n"
        "WorldStitch requires a PostgreSQL database — there is no SQLite fallback.\n"
        "Example: export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/worldstitch"
    )
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
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
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
