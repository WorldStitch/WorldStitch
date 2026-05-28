#!/bin/sh
# entrypoint.sh — WorldStitch server startup
#
# 1. Runs Alembic migrations so the schema is always up to date.
# 2. Starts the FastAPI server via uvicorn.
#
# Environment variables (set in docker-compose.yml or at runtime):
#   OPENAI_API_KEY   — required for AI features
#   VAULT_PATH       — path to note vault inside the container (default: /data/vault)
#   DATABASE_URL     — SQLAlchemy URL (default: sqlite:////data/worldstitch.db)
#   APP_ENV          — development | production | test  (default: production)
#   HOST             — bind host  (default: 0.0.0.0)
#   PORT             — bind port  (default: 8741)
#   WORKERS          — number of uvicorn workers (default: 1 — SQLite prefers single-writer)
#   LOG_LEVEL        — uvicorn log level: debug | info | warning (default: info)

set -e

: "${APP_ENV:=production}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8741}"
: "${WORKERS:=1}"
: "${LOG_LEVEL:=info}"
: "${DATABASE_URL:=sqlite:////data/worldstitch.db}"
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
