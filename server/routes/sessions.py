"""
Session Log endpoints — D&D campaign session tracking.

Routes support two storage backends selected by which ID param is supplied:

  campaign_id → new `play_sessions` table (preferred, campaign-scoped)
  vault_id    → legacy `session_logs` table (deprecated)

GET    /sessions?campaign_id=&skip=&limit=  — paginated list (play_sessions)
GET    /sessions?vault_id=&skip=&limit=     — paginated list (session_logs, deprecated)
GET    /sessions/{id}                       — get single session (auto-detects table)
POST   /sessions                            — create session
PUT    /sessions/{id}                       — update session
DELETE /sessions/{id}                       — soft delete
POST   /sessions/{id}/recap                 — generate AI recap from raw_notes
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from server.deps import get_ctx, get_current_user
from server.vault_access import resolve_vault

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Request / Response models
# ============================================================================


class SessionLogCreate(BaseModel):
    title: str
    campaign_id: Optional[str] = None  # preferred
    vault_id: Optional[str] = None  # deprecated alias
    session_date: str = ""
    summary: str = ""
    raw_notes: str = ""
    participants: str = ""
    xp_gained: int = 0
    loot_notes: str = ""


class SessionLogUpdate(BaseModel):
    title: Optional[str] = None
    session_date: Optional[str] = None
    summary: Optional[str] = None
    raw_notes: Optional[str] = None
    ai_recap: Optional[str] = None
    participants: Optional[str] = None
    xp_gained: Optional[int] = None
    loot_notes: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================


def _get_play_session_or_404(ctx: AppContext, session_id: str, campaign_id: Optional[str] = None) -> dict:
    session = ctx.storage.get_play_session(session_id, campaign_id=campaign_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _get_legacy_session_or_404(ctx: AppContext, user: User, session_id: str) -> dict:
    session = ctx.storage.get_session_log(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    resolve_vault(ctx, user, session.get("vault_id"))
    return session


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/")
async def list_sessions(
    campaign_id: Optional[str] = Query(None, description="Campaign ID — uses play_sessions table (preferred)"),
    vault_id: Optional[str] = Query(None, description="Deprecated: uses legacy session_logs table"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List sessions. campaign_id uses the new play_sessions table; vault_id uses the legacy table."""
    if campaign_id:
        items, total = ctx.storage.list_play_sessions(campaign_id, skip=skip, limit=limit)
        return {"items": items, "total": total, "skip": skip, "limit": limit}
    # Legacy path
    resolved_vault = resolve_vault(ctx, user, vault_id).id if vault_id else ""
    if resolved_vault:
        items, total = ctx.storage.list_session_logs(resolved_vault, skip=skip, limit=limit)
        return {"items": items, "total": total, "skip": skip, "limit": limit}
    return {"items": [], "total": 0, "skip": skip, "limit": limit}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    campaign_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Get a session. If campaign_id is supplied, look in play_sessions; otherwise try both tables."""
    if campaign_id:
        return _get_play_session_or_404(ctx, session_id, campaign_id=campaign_id)
    # Try play_sessions first, fall back to legacy
    session = ctx.storage.get_play_session(session_id)
    if session:
        return session
    return _get_legacy_session_or_404(ctx, user, session_id)


@router.post("/", status_code=201)
async def create_session(
    body: SessionLogCreate,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a session. campaign_id routes to play_sessions; vault_id routes to legacy table."""
    if body.campaign_id:
        data = body.model_dump(exclude={"vault_id"})
        data["created_by_user_id"] = user.id
        session_id = ctx.storage.save_play_session(body.campaign_id, data)
        return ctx.storage.get_play_session(session_id)
    # Legacy path
    data = body.model_dump(exclude={"campaign_id"})
    resolved_vault = resolve_vault(ctx, user, body.vault_id).id if body.vault_id else "default"
    data["vault_id"] = resolved_vault
    data["owner_id"] = user.id
    session_id = ctx.storage.save_session_log(data)
    return ctx.storage.get_session_log(session_id)


@router.put("/{session_id}")
async def update_session(
    session_id: str,
    body: SessionLogUpdate,
    campaign_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update a session."""
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    update["id"] = session_id
    if campaign_id:
        _get_play_session_or_404(ctx, session_id, campaign_id=campaign_id)
        ctx.storage.save_play_session(campaign_id, update)
        return ctx.storage.get_play_session(session_id)
    # Legacy path
    _get_legacy_session_or_404(ctx, user, session_id)
    ctx.storage.save_session_log(update)
    return ctx.storage.get_session_log(session_id)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    campaign_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Soft-delete a session."""
    if campaign_id:
        _get_play_session_or_404(ctx, session_id, campaign_id=campaign_id)
        ctx.storage.delete_play_session(session_id, campaign_id=campaign_id)
        return None
    # Legacy path
    _get_legacy_session_or_404(ctx, user, session_id)
    ctx.storage.soft_delete_session_log(session_id)
    return None


@router.post("/{session_id}/recap")
async def generate_recap(
    session_id: str,
    campaign_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Generate an AI recap for a session."""
    if campaign_id:
        session = _get_play_session_or_404(ctx, session_id, campaign_id=campaign_id)
    else:
        session = ctx.storage.get_play_session(session_id) or _get_legacy_session_or_404(ctx, user, session_id)

    if not ctx.has_ai():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI engine not available",
        )

    raw_notes = (session.get("raw_notes") or "").strip()
    if not raw_notes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No raw notes to summarize",
        )

    try:
        ai = ctx.require_ai()
        prompt = (
            "You are a D&D session chronicler. Summarize the following session notes "
            f"into a vivid, narrative-style recap for players: {raw_notes}"
        )
        response, _, _ = ai.ask(prompt)
        update = {"id": session_id, "ai_recap": response}
        if campaign_id:
            ctx.storage.save_play_session(campaign_id, update)
        else:
            ctx.storage.save_session_log(update)
        return {"ai_recap": response}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recap generation failed: {str(e)}",
        )
