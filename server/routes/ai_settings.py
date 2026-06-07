"""
AI API key and usage settings.

GET    /settings/ai                      — user's AI key status + quota
POST   /settings/ai/key                  — save personal OpenAI key
DELETE /settings/ai/key                  — remove personal key (revert to server key)

GET    /admin/ai-usage                   — admin: all users' usage stats
POST   /admin/users/{user_id}/ai-limit   — admin: set a user's monthly limit
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from server.deps import get_ctx, get_current_user, require_admin

router = APIRouter(tags=["ai-settings"])


# ── Request models ─────────────────────────────────────────────────────────────


class SaveKeyRequest(BaseModel):
    api_key: str


class SetLimitRequest(BaseModel):
    monthly_request_limit: int


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_store(ctx: AppContext):
    store = getattr(ctx.storage, "user_api_keys", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User API key store not available.",
        )
    return store


# ── User endpoints ─────────────────────────────────────────────────────────────


@router.get("/settings/ai")
def get_ai_settings(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the current user's AI key status and monthly quota."""
    return _get_store(ctx).get_settings(str(user.id))


@router.post("/settings/ai/key", status_code=204)
def save_ai_key(
    body: SaveKeyRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Save the user's personal OpenAI API key."""
    if not body.api_key.startswith("sk-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="API key must start with 'sk-'.",
        )
    _get_store(ctx).save_key(str(user.id), body.api_key)


@router.delete("/settings/ai/key", status_code=204)
def remove_ai_key(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Remove the user's personal key — they revert to the shared server key."""
    _get_store(ctx).remove_key(str(user.id))


# ── Admin endpoints ────────────────────────────────────────────────────────────


@router.get("/admin/ai-usage")
def admin_ai_usage(
    ctx: AppContext = Depends(get_ctx),
    _admin: User = Depends(require_admin),
):
    """Return AI usage stats for all users (admin only)."""
    raw_rows = _get_store(ctx).get_all_usage()

    enriched = []
    for row in raw_rows:
        u = ctx.users.get_user(row["user_id"])
        enriched.append(
            {
                **row,
                "username": u.username if u else row["user_id"],
                "email": u.email if u else "",
            }
        )
    return enriched


@router.post("/admin/users/{user_id}/ai-limit", status_code=204)
def admin_set_ai_limit(
    user_id: str,
    body: SetLimitRequest,
    ctx: AppContext = Depends(get_ctx),
    _admin: User = Depends(require_admin),
):
    """Set a user's monthly server-key request limit (admin only)."""
    if body.monthly_request_limit < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="monthly_request_limit must be >= 0.",
        )
    _get_store(ctx).set_limit(user_id, body.monthly_request_limit)
