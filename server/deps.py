"""
FastAPI dependency providers for WorldStitch server.

All route handlers receive AppContext and the current User via these
FastAPI dependencies, keeping routes thin and testable.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from server.auth_utils import decode_jwt
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User

_ctx: Optional[AppContext] = None

# ── Platform role sets ────────────────────────────────────────────────────────
# All nine platform roles:
#   owner    — platform super-admin (Evan / founding team)
#   admin    — platform admin
#   mod      — moderator
#   support  — support staff (read-heavy, limited write)
#   tester   — internal/beta tester
#   beta     — early-access user tier between tester and user
#   user     — standard registered user
#   guest    — reserved for future read-only no-account access
#   system   — bots and automated processes

PLATFORM_ROLES = {"owner", "admin", "mod", "support", "tester", "beta", "user", "guest", "system"}

# Users who can perform platform-level admin actions
PLATFORM_ADMIN = {"owner", "admin"}

# Users who can perform moderation-level actions
MOD_AND_ABOVE = {"owner", "admin", "mod"}

# Users who are eligible to use the platform-level OpenAI key as fallback
# (privileged internal accounts — not general beta/user/guest)
PLATFORM_KEY_ROLES = {"owner", "admin", "mod", "support", "tester", "system"}


def set_app_context(ctx: AppContext) -> None:
    """Called once at startup to register the AppContext."""
    global _ctx
    _ctx = ctx


def get_ctx() -> AppContext:
    """Return the shared AppContext. Raises 503 if not initialised."""
    if _ctx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application context not initialised.",
        )
    return _ctx


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    ctx: AppContext = Depends(get_ctx),
) -> User:
    """
    Extract and validate the Bearer token from the Authorization header.

    Returns the authenticated User or raises 401.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_jwt(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = ctx.users.get_user(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled.",
        )

    ctx.storage.set_user_context(
        user.id,
        is_admin=user.system_role in PLATFORM_ADMIN,
    )
    ctx.current_user_id = user.id
    return user


def require_permission(permission: str):
    """Dependency factory for route-level permission checks using system_role."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if permission == "admin" and user.system_role not in PLATFORM_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform admin required.",
            )
        if permission == "moderator" and user.system_role not in MOD_AND_ABOVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Moderator or above required.",
            )
        return user

    return Depends(dependency)


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Raises 403 if the current user is not a platform admin (owner or admin)."""
    if user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user
