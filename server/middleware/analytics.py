"""
Analytics middleware — auto-tracks every HTTP request as an `http.request` event.

Reads the X-Session-ID header for session tracking (client generates once per session).
Reads user_id from the Bearer JWT if present — never fails on bad/missing tokens.
Skips health, docs, openapi, and the analytics endpoints themselves.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

_SKIP_EXACT = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})
_SKIP_PREFIX = ("/admin/analytics",)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        path = request.url.path
        if path in _SKIP_EXACT or any(path.startswith(p) for p in _SKIP_PREFIX):
            return response

        try:
            user_id: Optional[str] = None
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                try:
                    from server.auth_utils import decode_jwt

                    payload = decode_jwt(auth.removeprefix("Bearer ").strip())
                    user_id = payload.get("sub") if isinstance(payload, dict) else None
                except Exception:
                    pass

            session_id = request.headers.get("x-session-id") or None

            from server.analytics import track

            asyncio.create_task(
                track(
                    "http.request",
                    user_id=user_id,
                    session_id=session_id,
                    method=request.method,
                    path=path,
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 1),
                )
            )
        except Exception:
            pass

        return response
