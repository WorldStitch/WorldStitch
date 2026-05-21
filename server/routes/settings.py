"""
Settings routes for WorldStitch FastAPI server.

Endpoints
---------
GET /settings   — return current app settings (safe subset, lowercase keys)
PUT /settings   — update settings (accepts lowercase or uppercase keys)
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from server.deps import get_ctx, get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])

# Keys that must never be returned to the client
_SENSITIVE_KEYS = {"OPENAI_API_KEY"}

# Keys that clients are allowed to update (uppercase canonical form)
_MUTABLE_KEYS = {
    "THEME",
    "FONT_SIZE",
    "SHOW_TOOLTIPS",
    "STARTUP_TAB",
    "COMPACT_MODE",
    "COMPLETION_MODEL",
    "EMBEDDING_MODEL",
    "MAX_TOKENS",
    "LOG_LEVEL",
    "PREFERRED_MODEL",
    "STREAMING_ENABLED",
    "AI_HISTORY_LIMIT",
}


@router.get("")
def get_settings(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(get_current_user),
):
    """Return current settings as lowercase keys, excluding sensitive values."""
    raw: Dict[str, Any] = {k.lower(): v for k, v in ctx.config._data.copy().items()}
    raw.pop("openai_api_key", None)
    raw["has_api_key"] = bool(getattr(ctx.config, "OPENAI_API_KEY", ""))
    return raw


@router.put("")
def update_settings(
    body: Dict[str, Any],
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(get_current_user),
):
    """Update allowed settings fields. Accepts lowercase or uppercase keys."""
    for key, value in body.items():
        upper_key = key.upper()
        if upper_key in _MUTABLE_KEYS:
            try:
                setattr(ctx.config, upper_key, value)
            except AttributeError:
                pass
    return get_settings(ctx=ctx, _user=_user)


class ConsentRequest(BaseModel):
    consent: bool


@router.get("/analytics")
def get_analytics_consent(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the current user's analytics consent preference."""
    consent = getattr(ctx.storage, "user_has_analytics_consent", lambda _: False)(user.id)
    return {"consent": consent}


@router.post("/analytics/consent")
def set_analytics_consent(
    body: ConsentRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Set the current user's analytics consent preference."""
    if hasattr(ctx.storage, "set_analytics_consent"):
        ctx.storage.set_analytics_consent(user.id, body.consent)
    return {"consent": body.consent}
