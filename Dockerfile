# ============================================================================
# WorldStitch — server-only Docker image
# ============================================================================
#
# Build:  docker build -t worldstitch .
# Run:    docker compose up
#
# The image intentionally excludes PyQt6 and all other desktop-only packages.
# The [desktop-only] lines in requirements.txt are stripped at build time.
#
# Data that must survive container restarts is stored under /data (see
# docker-compose.yml for the volume mounts).
# ============================================================================

FROM python:3.11-slim

# ── System deps ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python deps — strip desktop-only packages before installing ───────────────
COPY requirements.txt .
RUN grep -v '\[desktop-only\]' requirements.txt \
    | grep -v '^\s*#' \
    | grep -v '^\s*$' \
    > requirements.server.txt \
    && pip install --no-cache-dir -r requirements.server.txt

# ── Frontend deps (cached separately — only busts on package.json changes) ────
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd /app/frontend && npm ci

# ── Application code ──────────────────────────────────────────────────────────
COPY . .

# ── Build React frontend ──────────────────────────────────────────────────────
RUN cd /app/frontend && npx vite build \
    && rm -rf /app/frontend/node_modules

# ── Runtime directories (overridden by volume mounts in docker-compose) ───────
RUN mkdir -p /data/vault /data/logs

# ── Expose the API port ───────────────────────────────────────────────────────
EXPOSE 8741

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
