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

from server.context import AppContext
from server.deps import get_ctx, get_current_user, require_admin
from WorldStitch.models.user import User

router = APIRouter(tags=["ai-settings"])


# ── Request models ─────────────────────────────────────────────────────────────


class SaveKeyRequest(BaseModel):
    api_key: str


class SetLimitRequest(BaseModel):
    monthly_request_limit: int


# ── User endpoints ─────────────────────────────────────────────────────────────


@router.get("/settings/ai")
async def get_ai_settings(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the current user's AI key status and monthly quota."""
    return await ctx.storage.get_ai_settings(str(user.id))


@router.post("/settings/ai/key", status_code=204)
async def save_ai_key(
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
    await ctx.storage.save_personal_ai_key(str(user.id), body.api_key)


@router.delete("/settings/ai/key", status_code=204)
async def remove_ai_key(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Remove the user's personal key — they revert to the shared server key."""
    await ctx.storage.remove_personal_ai_key(str(user.id))


# ── Admin endpoints ────────────────────────────────────────────────────────────


@router.get("/admin/ai-usage")
async def admin_ai_usage(
    ctx: AppContext = Depends(get_ctx),
    _admin: User = Depends(require_admin),
):
    """Return AI usage stats for all users (admin only)."""
    raw_rows = await ctx.storage.get_all_ai_usage()

    enriched = []
    for row in raw_rows:
        u = await ctx.storage.get_user_by_id(row["user_id"])
        enriched.append(
            {
                **row,
                "username": u.username if u else row["user_id"],
                "email": u.email if u else "",
            }
        )
    return enriched


@router.post("/admin/users/{user_id}/ai-limit", status_code=204)
async def admin_set_ai_limit(
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
    await ctx.storage.set_ai_limit(user_id, body.monthly_request_limit)
