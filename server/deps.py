"""
FastAPI dependency providers for MythosEngine server.

All route handlers receive AppContext and the current User via these
FastAPI dependencies, keeping routes thin and testable.
"""

from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User
from server.auth_utils import decode_jwt

_ctx: Optional[AppContext] = None

PLATFORM_ADMIN = {"owner", "admin"}
MOD_AND_ABOVE = {"owner", "admin", "moderator"}


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
