"""
WorldStitch monitoring module.

Initialises Sentry error tracking (if SENTRY_DSN is set) and registers a
lightweight /metrics endpoint that returns basic health and uptime data as JSON.

Usage in app.py:
    from server.monitoring import init_sentry, metrics_router
    init_sentry()
    app.include_router(metrics_router)
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Record the process start time so /metrics can report uptime.
_START_TIME: float = time.monotonic()

metrics_router = APIRouter(tags=["monitoring"])


# ── Sentry initialisation ─────────────────────────────────────────────────────


def init_sentry() -> bool:
    """
    Initialise Sentry SDK if SENTRY_DSN is present in the environment.

    Returns True if Sentry was initialised successfully, False otherwise.
    Safe to call multiple times — re-initialises only when DSN is non-empty.
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.debug("Sentry not configured (SENTRY_DSN not set).")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        environment = os.getenv("APP_ENV", "development")
        release = os.getenv("SENTRY_RELEASE") or None

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            # Capture 10 % of transactions in production; 100 % in dev/staging.
            traces_sample_rate=0.1 if environment == "production" else 1.0,
            # Capture 10 % of profiled transactions (requires traces_sample_rate > 0).
            profiles_sample_rate=0.1 if environment == "production" else 1.0,
            integrations=[
                StarletteIntegration(transaction_style="endpoint"),
                FastApiIntegration(transaction_style="endpoint"),
            ],
        )
        logger.info("Sentry initialised (env=%s).", environment)
        return True
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed. Run: pip install sentry-sdk[fastapi]")
        return False
    except Exception as exc:
        logger.warning("Sentry initialisation failed: %s", exc)
        return False


# ── /metrics endpoint ─────────────────────────────────────────────────────────


@metrics_router.get("/metrics", tags=["monitoring"])
def metrics():
    """
    Lightweight health and uptime metrics endpoint.

    Returns a JSON object suitable for use by uptime monitors (UptimeRobot,
    Render health checks, etc.) as well as basic introspection.

    Fields
    ------
    status          "ok" — always present if the server is running.
    uptime_seconds  Seconds since this process started.
    sentry_enabled  True if Sentry is active in this process.
    environment     Value of APP_ENV env var (defaults to "development").
    """
    uptime = time.monotonic() - _START_TIME

    sentry_active = False
    try:
        import sentry_sdk

        sentry_active = bool(sentry_sdk.get_client().dsn)
    except Exception:
        pass

    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 2),
        "sentry_enabled": sentry_active,
        "environment": os.getenv("APP_ENV", "development"),
    }
