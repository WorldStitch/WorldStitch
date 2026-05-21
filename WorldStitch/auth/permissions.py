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
ROLE_GM = "gm"
ROLE_PLAYER = "player"

ALL_ROLES = (ROLE_ADMIN, ROLE_GM, ROLE_PLAYER)

# Rank used for "at least this role" checks.  Higher = more privilege.
_SYSTEM_ROLE_RANK = {ROLE_PLAYER: 1, ROLE_GM: 2, ROLE_ADMIN: 3}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _highest_role(user) -> str:
    """Return the most-privileged system role the user holds."""
    best, best_rank = ROLE_PLAYER, 0
    for r in user.roles or []:
        rank = _SYSTEM_ROLE_RANK.get(r, 0)
        if rank > best_rank:
            best, best_rank = r, rank
    return best


def is_admin(ctx: "AppContext") -> bool:
    """Return True if the currently logged-in user has the admin role."""
    user = ctx.current_user
    return user is not None and ROLE_ADMIN in user.roles


def is_gm(ctx: "AppContext") -> bool:
    """Return True if the currently logged-in user has the gm role."""
    user = ctx.current_user
    return user is not None and ROLE_GM in user.roles


def is_gm_or_admin(ctx: "AppContext") -> bool:
    """Return True if the current user is a GM or an admin."""
    user = ctx.current_user
    if user is None:
        return False
    roles = set(user.roles or [])
    return bool(roles & {ROLE_ADMIN, ROLE_GM})


def require_admin(ctx: "AppContext") -> None:
    """
    Raise PermissionError if the current user is not an admin.

    Usage::

        from WorldStitch.auth.permissions import require_admin
        require_admin(ctx)   # raises if not admin
    """
    if not is_admin(ctx):
        raise PermissionError("Admin access is required for this action.")


def require_gm_or_admin(ctx: "AppContext") -> None:
    """
    Raise PermissionError if the current user is neither a GM nor an admin.

    Usage::

        from WorldStitch.auth.permissions import require_gm_or_admin
        require_gm_or_admin(ctx)   # raises if not gm/admin
    """
    if not is_gm_or_admin(ctx):
        raise PermissionError("GM or Admin access is required for this action.")
