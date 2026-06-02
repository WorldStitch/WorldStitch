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

# ── System deps (including Node.js for frontend build) ───────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libsqlite3-dev \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python deps — strip desktop-only packages before installing ───────────────
# Cached until requirements.txt changes.
COPY requirements.txt .
RUN grep -v '\[desktop-only\]' requirements.txt \
    | grep -v '^\s*#' \
    | grep -v '^\s*$' \
    > requirements.server.txt \
    && pip install --no-cache-dir -r requirements.server.txt

# ── Frontend Node deps — cached until package-lock.json changes ───────────────
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# ── Application code (cache busts here on any source change) ─────────────────
COPY . .

# ── Build React frontend then purge Node from the final image ─────────────────
RUN cd /app/frontend && npx vite build \
    && rm -rf /app/frontend/node_modules \
    && apt-get purge -y nodejs npm && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# ── Runtime directories (overridden by volume mounts in docker-compose) ───────
RUN mkdir -p /data/vault /data/logs

# ── Expose the API port ───────────────────────────────────────────────────────
EXPOSE 8741

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
