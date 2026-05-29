"""
Dashboard routes for WorldStitch FastAPI server.

Endpoints
---------
GET /dashboard/stats  — note/character/session counts
GET /dashboard/recent — most-recently-modified notes
"""

from fastapi import APIRouter, Depends, Query

from server.deps import get_ctx, get_current_user
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(
    campaign_id: str = "",
    vault_id: str = Query(default=""),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return content counts scoped to the active vault."""
    effective_id = campaign_id or vault_id or ""

    notes_count = ctx.storage.count_notes(vault_id=effective_id)

    try:
        folders = ctx.storage.list_folders(vault_id=effective_id)
        folder_count = len(folders) if isinstance(folders, list) else 0
    except Exception:
        folder_count = 0

    try:
        chars = ctx.storage.list_characters(campaign_id=effective_id or None, vault_id=effective_id)
        char_count = len(chars) if isinstance(chars, list) else 0
    except Exception:
        char_count = 0

    sessions_total = 0
    if effective_id and hasattr(ctx.storage, "list_play_sessions"):
        try:
            _, sessions_total = ctx.storage.list_play_sessions(effective_id, limit=0)
        except Exception:
            sessions_total = 0
    if not sessions_total:
        try:
            _, sessions_total = ctx.storage.list_session_logs(vault_id=effective_id)
        except Exception:
            sessions_total = _count_meta(ctx, "sessions")

    timeline_events = _count_timeline(ctx)

    return {
        "notes": notes_count,
        "folders": folder_count,
        "characters": char_count,
        "quests": 0,
        "timeline_events": timeline_events,
        "sessions": sessions_total,
    }


@router.get("/recent")
def recent(
    vault_id: str = Query(default=""),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the 10 most recently modified notes for the given vault."""
    try:
        if hasattr(ctx.storage, "_session"):
            import json as _json

            from WorldStitch.storage.sqlite_backend import NoteRecord

            with ctx.storage._session() as session:
                q = session.query(NoteRecord).filter(NoteRecord.is_deleted.is_not(True))
                if vault_id:
                    q = q.filter(NoteRecord.vault_id == vault_id)
                if not getattr(ctx.storage, "_is_admin", False):
                    q = q.filter(NoteRecord.owner_id == user.id)
                records = q.order_by(NoteRecord.created_at.desc()).limit(10).all()
                items = []
                for rec in records:
                    data = {}
                    try:
                        data = _json.loads(rec.data or "{}")
                    except Exception:
                        pass
                    items.append(
                        {
                            "id": rec.id,
                            "title": rec.title or data.get("title", "Untitled"),
                            "last_modified": rec.created_at.isoformat() if rec.created_at else None,
                            "vault_id": rec.vault_id,
                        }
                    )
                return items
    except Exception:
        pass

    # Fallback: filesystem-based (HybridStorage)
    paths = ctx.storage.list_notes()
    items = []
    for p in paths:
        try:
            meta = ctx.storage.get_note_metadata(p)
            items.append(
                {
                    "id": p,
                    "title": p.split("/")[-1].removesuffix(".md"),
                    "last_modified": meta.get("modified"),
                }
            )
        except Exception:
            items.append({"id": p, "title": p.split("/")[-1].removesuffix(".md"), "last_modified": None})
    items.sort(key=lambda x: x.get("last_modified") or "", reverse=True)
    return items[:10]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _count_meta(ctx: AppContext, subfolder: str) -> int:
    """Count JSON files in a .dnd_meta subfolder."""
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
