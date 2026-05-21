"""
WorldStitch FastAPI application.

Creates the FastAPI app, wires up AppContext, and registers all route
modules.  Uvicorn points at ``server.app:app``.

Start from the project root (the directory containing both
``WorldStitch/`` and ``server/``):

    uvicorn server.app:app --host 127.0.0.1 --port 8741 --reload

The Electron ``main.cjs`` starts this automatically in production.
"""

import logging
import sys
import threading
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Add parent directory so WorldStitch package is importable
_parent = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_parent))

from fastapi.responses import JSONResponse

from WorldStitch.config.config import Config
from WorldStitch.context.app_context import AppContext
from server.deps import set_app_context
from server.limiter import limiter
from server.middleware.logging import LoggingMiddleware
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
    sessions,
    settings,
    users,
    vaults,
    ws,
)

logger = logging.getLogger(__name__)


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
    ctx = AppContext(cfg)

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
                ctx.ai._index_ready = True
                logger.info("AI index build complete")
            except Exception as exc:
                logger.warning("AI index build failed: %s", exc)

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
    description="REST API for the WorldStitch D&D campaign management platform.",
    lifespan=lifespan,
)

# Rate-limiting (slowapi)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(LoggingMiddleware)

# Allow the Vite dev server (port 5173) and production Electron renderer
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8741",
        "http://127.0.0.1:8741",
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
        ctx.analytics.track(
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
app.include_router(vaults.router, prefix="/vaults", tags=["vaults"])
app.include_router(groups.router, prefix="/groups", tags=["groups"])
app.include_router(ws.router, tags=["ws"])
app.include_router(debug.router, prefix="/debug", tags=["debug"])
app.include_router(admin_analytics.router)


# ── Health check ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
def health():
    """Liveness probe used by the Electron launcher to detect API readiness."""
    return {"status": "ok", "service": "WorldStitch"}
