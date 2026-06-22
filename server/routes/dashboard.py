"""
Dashboard routes for WorldStitch FastAPI server.

Endpoints
---------
GET /dashboard/stats  — note/character/session counts
GET /dashboard/recent — most-recently-modified notes
"""

import logging

from fastapi import APIRouter, Depends, Query

from server.context import AppContext
from server.deps import get_ctx, get_current_user
from server.storage import Actor
from WorldStitch.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def stats(
    campaign_id: str = "",
    vault_id: str = Query(default=""),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return content counts scoped to the active vault."""
    effective_id = campaign_id or vault_id or ""
    actor = Actor.from_user(user)

    notes_count = await ctx.storage.count_notes(actor, vault_id=effective_id)

    try:
        folders = await ctx.storage.list_all_folders(actor, vault_id=effective_id)
        folder_count = len(folders) if isinstance(folders, list) else 0
    except Exception:
        logger.warning("dashboard/stats: could not count folders for vault_id=%s", effective_id)
        folder_count = 0

    try:
        chars = await ctx.storage.list_characters(campaign_id=effective_id or None, vault_id=effective_id)
        char_count = len(chars) if isinstance(chars, list) else 0
    except Exception:
        logger.warning("dashboard/stats: could not count characters for vault_id=%s", effective_id)
        char_count = 0

    sessions_total = 0
    if effective_id:
        try:
            _, sessions_total = await ctx.storage.list_play_sessions(effective_id, limit=0)
        except Exception:
            logger.warning("dashboard/stats: could not count play sessions for vault_id=%s", effective_id)
            sessions_total = 0
    if not sessions_total and effective_id:
        try:
            _, sessions_total = await ctx.storage.list_session_logs(vault_id=effective_id)
        except Exception:
            sessions_total = 0

    return {
        "notes": notes_count,
        "folders": folder_count,
        "characters": char_count,
        "sessions": sessions_total,
    }


@router.get("/recent")
async def recent(
    vault_id: str = Query(default=""),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the 10 most recently modified notes for the given vault."""
    actor = Actor.from_user(user)
    try:
        notes = await ctx.storage.list_all_notes(actor, vault_id=vault_id, limit=10)
        return [
            {
                "id": note.id,
                "title": note.title or "Untitled",
                "last_modified": note.last_modified.isoformat() if note.last_modified else None,
                "vault_id": note.vault_id,
            }
            for note in notes
        ]
    except Exception:
        logger.warning("dashboard/recent: DB query failed", exc_info=True)
        return []
