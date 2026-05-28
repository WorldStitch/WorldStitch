# WorldStitch/auth/permissions.py
"""
Role constants and permission helpers.

Roles are stored as strings in User.roles so they survive serialization.
Use these constants everywhere instead of raw strings to avoid typos.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from WorldStitch.context.app_context import AppContext

# ── Role constants ─────────────────────────────────────────────────────────────
ROLE_ADMIN = "admin"

ALL_ROLES = (ROLE_ADMIN,)


# ── Helpers ───────────────────────────────────────────────────────────────────


def is_admin(ctx: "AppContext") -> bool:
    """Return True if the currently logged-in user has the admin role."""
    user = ctx.current_user
    return user is not None and ROLE_ADMIN in user.roles


def require_admin(ctx: "AppContext") -> None:
    """
    Raise PermissionError if the current user is not an admin.

    Usage::

        from WorldStitch.auth.permissions import require_admin
        require_admin(ctx)   # raises if not admin
    """
    if not is_admin(ctx):
        raise PermissionError("Admin access is required for this action.")
