"""
WorldStitch FastAPI application.

Creates the FastAPI app, wires up AppContext, and registers all route
modules.  Uvicorn points at ``server.app:app``.

Start from the project root (the directory containing both
``WorldStitch/`` and ``server/``):

    uvicorn server.app:app --host 127.0.0.1 --port 8741 --reload
"""

import asyncio
import logging
import sys
import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Add parent directory so WorldStitch package is importable
_parent = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_parent))

from fastapi.responses import JSONResponse

from server.context import AppContext
from server.db import get_engine, get_session_factory, run_startup_migrations
from server.deps import set_app_context
from server.limiter import _rate_limit_enabled, limiter
from server.middleware.analytics import AnalyticsMiddleware
from server.middleware.logging import LoggingMiddleware
from server.monitoring import init_sentry, metrics_router
from server.routes import (
    admin_analytics,
    ai,
    ai_settings,
    auth,
    campaigns,
    characters,
    dashboard,
    debug,
    groups,
    invites,
    maps,
    notes,
    relationships,
    sessions,
    settings,
    users,
    vault_invites,
    vaults,
    waitlist,
    ws,
)
from server.storage import AsyncStorage
from WorldStitch.config.config import Config

logger = logging.getLogger(__name__)

# Initialise Sentry as early as possible (before route handlers are defined).
init_sentry()


# ── App lifespan ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Bootstrap AppContext and logging once at server startup."""
    # Initialise file + in-memory logging before anything else so all
    # startup messages land in the log file.
    try:
        from WorldStitch.utils.logging_setup import (  # noqa: F401
            APP_SESSION_LOG_HANDLER,
            file_handler,
        )

        root = logging.getLogger()
        if not any(isinstance(h, type(file_handler)) for h in root.handlers):
            root.addHandler(file_handler)
            root.addHandler(APP_SESSION_LOG_HANDLER)
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        logger.warning("Could not configure file logging: %s", exc)

    cfg = Config()

    if not cfg.API_KEY_ENCRYPTION_SECRET:
        logger.warning("WARNING: API_KEY_ENCRYPTION_SECRET not set — user API keys stored in plaintext")

    # Apply schema migrations before serving traffic. Alembic is sync-only,
    # so this runs a short-lived sync engine in a worker thread.
    await asyncio.to_thread(run_startup_migrations)

    storage = AsyncStorage(
        get_session_factory(),
        get_engine(),
        vault_path=getattr(cfg, "VAULT_PATH", None),
    )
    ctx = AppContext(cfg, storage)

    # Wire up AI engine if an API key is present
    api_key = getattr(cfg, "OPENAI_API_KEY", "")
    if api_key:
        try:
            from WorldStitch.ai.core.model_router import get_model_backend

            ctx.ai = get_model_backend(cfg, storage=ctx.storage)
            ctx.ai._index_ready = False
            logger.info("AI engine initialised.")
        except Exception as exc:
            logger.warning("AI engine failed to initialise: %s", exc)

    # Build the AI vector index in a background thread so startup is non-blocking.
    if ctx.has_ai():

        def _build_index_bg() -> None:
            try:
                ctx.ai.index_manager.build_index()
                logger.info("AI index build complete")
            except Exception as exc:
                # Log the failure but still mark the index as "ready" so the
                # frontend banner ("Vault index is building…") clears.  AI
                # still works via the recent-notes fallback; semantic search
                # simply returns an empty list when the retriever is None.
                logger.warning("AI index build failed (will use note fallback): %s", exc)
            finally:
                ctx.ai._index_ready = True

        threading.Thread(target=_build_index_bg, daemon=True).start()

    application.state.ctx = ctx
    set_app_context(ctx)
    logger.info("WorldStitch server ready. Vault: %s", getattr(cfg, "VAULT_PATH", "?"))
    yield
    logger.info("WorldStitch server shutting down.")


# ── FastAPI instance ──────────────────────────────────────────────────────────

app = FastAPI(
    title="WorldStitch API",
    version="1.0.0",
    description="REST API for the WorldStitch creative worldbuilding platform.",
    lifespan=lifespan,
)

# ── Rate-limiting (slowapi) ───────────────────────────────────────────────────


async def _custom_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a JSON 429 with Retry-After and X-RateLimit-* headers."""
    retry_after = 60
    limit_value = str(exc.detail) if exc.detail else "unknown"
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "retry_after": retry_after,
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    response.headers["X-RateLimit-Limit"] = limit_value
    response.headers["X-RateLimit-Remaining"] = "0"
    return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _custom_rate_limit_handler)

if _rate_limit_enabled:
    from slowapi.middleware import SlowAPIMiddleware

    app.add_middleware(SlowAPIMiddleware)
else:
    logger.info("Rate limiting disabled (RATE_LIMIT_ENABLED=false)")

app.add_middleware(AnalyticsMiddleware)
app.add_middleware(LoggingMiddleware)

# Allow the Vite dev server (port 5173) and same-origin production requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8741",
        "http://127.0.0.1:8741",
        "https://app.worldstitch.app",
        "https://worldstitch.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global unhandled exception handler ───────────────────────────────────────


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for any exception that escapes a route.

    Logs the full traceback to the app log file so crashes are never
    silently swallowed, then returns a safe JSON 500 to the client.
    """
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    # Track the route exception — never log request/response body.
    try:
        ctx = request.app.state.ctx
        user_id = ""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            from server.auth_utils import decode_jwt

            payload = decode_jwt(auth_header.removeprefix("Bearer ").strip())
            user_id = payload.get("sub", "") if isinstance(payload, dict) else ""
        await ctx.storage.track(
            "error.route_exception",
            user_id=user_id,
            data={"route": request.url.path, "status_code": 500},
        )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. See the server log for details."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

# WebSocket route registered directly on the app (not through APIRouter +
# prefix) to avoid a FastAPI/Starlette bug where prefix-based WebSocket route
# resolution fails — requests reach /api/ws but the prefixed router doesn't
# match them.  Must also be first so it wins before the StaticFiles Mount("/")
# which handles websocket scopes too (Match.FULL for any path).
app.add_api_websocket_route("/api/ws", ws.websocket_events)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(campaigns.router, prefix="/campaigns", tags=["campaigns"])
app.include_router(notes.router, prefix="/notes", tags=["notes"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(maps.router, prefix="/maps", tags=["maps"])
app.include_router(characters.router, prefix="/characters", tags=["characters"])
app.include_router(ai.router)
app.include_router(ai_settings.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(invites.router, prefix="/invites", tags=["invites"])
app.include_router(vault_invites.router, tags=["vault-invites"])
app.include_router(vaults.router, prefix="/vaults", tags=["vaults"])
app.include_router(groups.router, prefix="/groups", tags=["groups"])
app.include_router(debug.router, prefix="/debug", tags=["debug"])
app.include_router(admin_analytics.router)
app.include_router(relationships.router, prefix="/relationships", tags=["relationships"])
app.include_router(waitlist.router)
app.include_router(metrics_router)


# ── Health check ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
def health():
    """Liveness probe."""
    return {"status": "ok", "service": "WorldStitch"}


# ── Serve React frontend ──────────────────────────────────────────────────────
# Use StaticFiles(html=True) instead of a catch-all GET route.
# A mount is checked AFTER all FastAPI routes, so API endpoints are never
# shadowed and non-GET methods (POST /vaults/, etc.) work correctly.
from pathlib import Path as _Path

_frontend_dist = _Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
