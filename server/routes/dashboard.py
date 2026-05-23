"""
Dashboard routes for WorldStitch FastAPI server.

Endpoints
---------
GET /dashboard/stats  — note/character/session counts
GET /dashboard/recent — most-recently-modified notes
"""

from fastapi import APIRouter, Depends, Query

from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from server.deps import get_ctx, get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(
    campaign_id: str = "",
    vault_id: str = Query(default=""),  # deprecated alias for campaign_id
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(get_current_user),
):
    """Return content counts. Scoped by campaign_id when provided (vault_id is deprecated)."""
    effective_id = campaign_id or vault_id or ""

    notes_count = ctx.storage.count_notes(vault_id=effective_id)
    folders = ctx.storage.list_folders(vault_id=vault_id)
    characters = len(ctx.storage.list_characters(campaign_id=effective_id or None, vault_id=vault_id))

    sessions_total = 0
    if effective_id and hasattr(ctx.storage, "list_play_sessions"):
        try:
            _, sessions_total = ctx.storage.list_play_sessions(effective_id, limit=0)
        except Exception:
            sessions_total = 0
    if not sessions_total:
        try:
            _, sessions_total = ctx.storage.list_session_logs(vault_id=vault_id)
        except Exception:
            sessions_total = _count_meta(ctx, "sessions")
    timeline_events = _count_timeline(ctx)

    return {
        "notes": notes_count,
        "folders": len(folders),
        "characters": characters,
        "quests": 0,  # Quest model not yet implemented
        "timeline_events": timeline_events,
        "sessions": sessions_total,
    }


@router.get("/recent")
def recent(
    ctx: AppContext = Depends(get_ctx),
    _user: User = Depends(get_current_user),
):
    paths = ctx.storage.list_notes()
    items = []
    for p in paths:
        try:
            meta = ctx.storage.get_note_metadata(p)
            items.append(
                {
                    "id": p,
                    "title": p.split("/")[-1].removesuffix(".md"),
                    "modified_date": meta.get("modified"),
                }
            )
        except Exception:
            items.append({"id": p, "title": p.split("/")[-1].removesuffix(".md"), "modified_date": None})

    # Sort newest-first and return top 10
    items.sort(key=lambda x: x.get("modified_date") or "", reverse=True)
    return items[:10]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_meta(ctx: AppContext, subfolder: str) -> int:
    """Count JSON files in a .dnd_meta subfolder (HybridStorage / SQLiteBackend)."""
    try:
        from pathlib import Path

        vault_path = getattr(ctx.storage, "vault_path", None)
        if vault_path:
            d = Path(vault_path) / ".dnd_meta" / subfolder
            if d.is_dir():
                return len(list(d.glob("*.json")))
    except Exception:
        pass
    return 0


def _count_timeline(ctx: AppContext) -> int:
    """Count timeline events if the storage supports it."""
    try:
        events = ctx.storage.read_timeline()
        return len(events)
    except Exception:
        return 0
