#!/bin/sh
# entrypoint.sh — WorldStitch server startup
#
# 1. Runs Alembic migrations so the schema is always up to date.
# 2. Starts the FastAPI server via uvicorn.
#
# Required environment variables:
#   DATABASE_URL     — PostgreSQL connection URL (e.g. postgresql+psycopg2://user:pass@host/db)
#
# Optional environment variables:
#   OPENAI_API_KEY   — required for AI features
#   VAULT_PATH       — path to note vault inside the container (default: /data/vault)
#   APP_ENV          — development | production | test  (default: production)
#   HOST             — bind host  (default: 0.0.0.0)
#   PORT             — bind port  (default: 8741)
#   WORKERS          — number of uvicorn workers (default: 1)
#                      IMPORTANT: keep at 1 when using the in-memory WebSocket hub.
#                      Multiple workers each have an isolated hub; cross-worker
#                      presence broadcasts and collaboration features will not work.
#   LOG_LEVEL        — uvicorn log level: debug | info | warning (default: info)

set -e

# DATABASE_URL is required — fail fast if not set
if [ -z "${DATABASE_URL}" ]; then
    echo "ERROR: DATABASE_URL environment variable is not set." >&2
    echo "WorldStitch requires a PostgreSQL database — there is no SQLite fallback." >&2
    echo "Example: export DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/worldstitch" >&2
    exit 1
fi

: "${APP_ENV:=production}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8741}"
: "${WORKERS:=1}"
: "${LOG_LEVEL:=info}"
: "${VAULT_PATH:=/data/vault}"

export APP_ENV DATABASE_URL VAULT_PATH

echo "==> [entrypoint] APP_ENV=${APP_ENV}"
echo "==> [entrypoint] DATABASE_URL=${DATABASE_URL}"
echo "==> [entrypoint] VAULT_PATH=${VAULT_PATH}"

# ── Apply database migrations ─────────────────────────────────────────────────
echo "==> [entrypoint] Running Alembic migrations..."
alembic upgrade head

# ── Start the API server ──────────────────────────────────────────────────────
echo "==> [entrypoint] Starting uvicorn on ${HOST}:${PORT} (workers=${WORKERS})"
exec uvicorn server.app:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}"
