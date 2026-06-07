"""Shared slowapi rate-limiter instance.

Imported by both server/app.py (to mount middleware) and route modules
(to apply per-endpoint limits) so there is only one Limiter object.

Configuration via environment variables:
  RATE_LIMIT_ENABLED  — set to "false" (case-insensitive) to disable in local dev
  REDIS_URL           — if set, use Redis as the storage backend; otherwise in-memory
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def get_user_or_ip(request: Request) -> str:
    """
    Key function for authenticated routes.

    Prefer a user-specific identifier so rate limits are per-user rather than
    per-IP (important when multiple users share a NAT'd address).  Falls back
    to the remote IP for unauthenticated requests.
    """
    user = getattr(getattr(request, "state", None), "user", None)
    if user is not None:
        uid = getattr(user, "id", None) or getattr(user, "sub", None)
        if uid:
            return str(uid)
    return get_remote_address(request)


_rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"

# Default limit applied to every route that does not have its own decorator.
# When rate limiting is disabled (local dev), use a very high limit so the
# middleware is still registered but effectively does nothing.
_default_limit = "200/minute" if _rate_limit_enabled else "999999/minute"

_redis_url = os.getenv("REDIS_URL", "")

if _redis_url:
    from limits.storage import RedisStorage

    _storage = RedisStorage(_redis_url)
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[_default_limit],
        storage_uri=_redis_url,
    )
else:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[_default_limit],
    )
