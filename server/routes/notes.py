"""
Note and folder endpoints.

GET /notes — list notes (uses search_notes under the hood)
GET /notes/search?q= — search notes
GET /notes/{id} — read note by id
POST /notes — create note
PUT /notes/{id} — update note (title, content, tags, meta, folder_id, permissions, links)
DELETE /notes/{id} — delete note
POST /notes/move — move note to different folder

POST /notes/{id}/tags — add a tag
DELETE /notes/{id}/tags/{tag} — remove a tag
PUT /notes/{id}/meta — update metadata dict

GET /notes/folders — list folders
POST /notes/folders — create folder
PUT /notes/folders/{id} — rename/update folder
DELETE /notes/folders/{id} — delete folder

NOTE: storage.list_notes() returns List[str] (file paths), NOT Note objects.
We use search_notes("") or get_note_by_id() for Note objects, and the
NoteManager / FolderManager for all CRUD.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user
from server.realtime import hub
from server.vault_access import resolve_vault

router = APIRouter()
_RESOURCE_PERMISSION_RANK = {"read": 1, "write": 2}


def _normalize_resource_permissions(permissions: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Keep resource-level permissions limited to read/write.
    Legacy 'admin' resource roles are downgraded to 'write'.
    """
    normalized: Dict[str, str] = {}
    for subject_id, permission in (permissions or {}).items():
        if not subject_id:
            continue
        value = (permission or "").strip().lower()
        if value == "admin":
            value = "write"
        if value in _RESOURCE_PERMISSION_RANK:
            normalized[subject_id] = value
    return normalized


# ============================================================================
# Request/Response models
# ============================================================================


class NoteListItem(BaseModel):
    """Item in note list response — includes enough for tree + filter display."""

    id: str
    title: str
    folder_id: Optional[str] = None
    tags: List[str] = []
    group_id: Optional[str] = None
    owner_id: str = ""
    is_deleted: bool = False
    created_at: datetime
    last_modified: datetime
    snippet: Optional[str] = None  # FTS5 highlighted excerpt, present on search results


class NoteDetail(BaseModel):
    """Full note response — every field the Note model exposes."""

    id: str
    title: str
    content: str
    folder_id: Optional[str] = None
    vault_id: str
    tags: List[str] = []
    group_id: Optional[str] = None
    permissions: Dict[str, str] = {}
    links: List[str] = []
    attachments: List[str] = []
    ai_summary: Optional[str] = None
    meta: Dict[str, str] = {}
    owner_id: str = ""
    is_deleted: bool = False
    created_at: datetime
    last_modified: datetime


class CreateNoteRequest(BaseModel):
    """Request body for POST /notes"""

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field("", max_length=500_000)
    folder_id: Optional[str] = Field(None, max_length=200)
    tags: List[str] = Field(default_factory=list, max_length=50)
    meta: Dict[str, str] = {}
    vault_id: Optional[str] = Field(default=None, max_length=100)


class UpdateNoteRequest(BaseModel):
    """Request body for PUT /notes/{id}"""

    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, max_length=500_000)
    tags: Optional[List[str]] = Field(None, max_length=50)
    folder_id: Optional[str] = Field("__UNSET__", max_length=200)  # sentinel: None means "remove from folder"
    meta: Optional[Dict[str, str]] = None
    permissions: Optional[Dict[str, str]] = None
    links: Optional[List[str]] = None
    group_id: Optional[str] = Field("__UNSET__", max_length=100)


class MoveNoteRequest(BaseModel):
    """Request body for POST /notes/move"""

    note_id: str = Field(..., max_length=200)
    dest_folder_id: Optional[str] = Field(None, max_length=200)


class TagRequest(BaseModel):
    """Request body for POST /notes/{id}/tags"""

    tag: str = Field(..., min_length=1, max_length=50)


class MetaUpdateRequest(BaseModel):
    """Request body for PUT /notes/{id}/meta"""

    meta: Dict[str, str]


class CreateRelationshipRequest(BaseModel):
    """Request body for POST /notes/{id}/relationships"""

    target_id: str = Field(..., max_length=500, description="Target note ID or label")
    label: Optional[str] = Field(None, max_length=500)


class CreateFolderRequest(BaseModel):
    """Request body for POST /notes/folders"""

    name: str = Field(..., min_length=1, max_length=200)
    parent_id: Optional[str] = Field(None, max_length=100)
    vault_id: Optional[str] = Field(None, max_length=100)


class UpdateFolderRequest(BaseModel):
    """Request body for PUT /notes/folders/{id}"""

    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)


class FolderResponse(BaseModel):
    """Folder response"""

    id: str
    name: str
    vault_id: str
    parent_id: Optional[str] = None
    description: Optional[str] = None
    note_ids: List[str] = []
    created_at: datetime
    last_modified: datetime


# ============================================================================
# Helpers
# ============================================================================


def _note_to_list_item(note) -> NoteListItem:
    """Convert a Note model to a list item response."""
    return NoteListItem(
        id=note.id,
        title=note.title,
        folder_id=getattr(note, "folder_id", None),
        tags=getattr(note, "tags", []) or [],
        group_id=getattr(note, "group_id", None),
        owner_id=getattr(note, "owner_id", ""),
        is_deleted=getattr(note, "is_deleted", False),
        created_at=note.created_at,
        last_modified=note.last_modified,
    )


def _note_to_detail(note) -> NoteDetail:
    """Convert a Note model to a full detail response."""
    return NoteDetail(
        id=note.id,
        title=note.title,
        content=getattr(note, "content", "") or "",
        folder_id=getattr(note, "folder_id", None),
        vault_id=getattr(note, "vault_id", ""),
        tags=getattr(note, "tags", []) or [],
        group_id=getattr(note, "group_id", None),
        permissions=getattr(note, "permissions", {}) or {},
        links=getattr(note, "links", []) or [],
        attachments=getattr(note, "attachments", []) or [],
        ai_summary=getattr(note, "ai_summary", None),
        meta=getattr(note, "meta", {}) or {},
        owner_id=getattr(note, "owner_id", ""),
        is_deleted=getattr(note, "is_deleted", False),
        created_at=note.created_at,
        last_modified=note.last_modified,
    )


def _folder_to_response(folder, ctx, user) -> FolderResponse:
    """Convert a Folder model to a response."""
    return FolderResponse(
        id=folder.id,
        name=folder.name,
        vault_id=getattr(folder, "vault_id", ""),
        parent_id=getattr(folder, "parent_id", None),
        description=getattr(folder, "description", None),
        note_ids=getattr(folder, "note_ids", []) or [],
        created_at=folder.created_at,
        last_modified=folder.last_modified,
    )


def _resolve_vault_id(ctx: AppContext, user: User, requested_vault_id: Optional[str] = None) -> str:
    return resolve_vault(ctx, user, requested_vault_id).id


def _set_user_ctx(ctx: AppContext, user: User) -> None:
    """Set the per-request user context on the storage backend.

    This must be called at the start of every route handler that reads or
    writes user-owned data so that the storage-level ACL checks use the
    correct identity.
    """
    ctx.storage.set_user_context(
        user.id,
        is_admin=user.system_role in PLATFORM_ADMIN,
    )


def _get_note_or_404(ctx, note_id):
    """Get note by ID or raise 404."""
    note = ctx.notes.get_note(note_id)
    if not note:
        # Try reading by path (for file-based notes)
        try:
            content = ctx.storage.read_note(note_id)
            from MythosEngine.models.note import Note as NoteModel

            note = NoteModel(
                id=note_id,
                owner_id="",
                vault_id="default",
                title=note_id.rsplit("/", 1)[-1].replace(".md", ""),
                content=content,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )
    return note


# ============================================================================
# Note endpoints
# ============================================================================


# IMPORTANT: /search must come BEFORE /{note_id} to avoid being caught
# by the path parameter route.
@router.get("/search")
async def search_notes(
    q: str = Query(..., min_length=1, description="Search query"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    mode: str = Query("fts", description="Search mode: fts | semantic | hybrid"),
    folder: Optional[str] = Query(None, description="Filter by folder prefix"),
    tags: Optional[str] = Query(None, description="Comma-separated tags (note must have ALL)"),
    date_from: Optional[str] = Query(None, description="Filter notes created on/after ISO date"),
    date_to: Optional[str] = Query(None, description="Filter notes created on/before ISO date"),
    vault_id: Optional[str] = Query(None, description="Vault to search inside"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Search notes by title, content, and tags.

    Modes:
    - ``fts``      — FTS5 full-text search with BM25 ranking and snippet highlighting
                     (falls back to LIKE search if FTS5 unavailable)
    - ``semantic`` — Vector similarity search via VectorIndexManager
    - ``hybrid``   — Runs both; merges results weighted FTS×0.6 + semantic×0.4
    """
    try:
        _set_user_ctx(ctx, user)
        vault_id = _resolve_vault_id(ctx, user, vault_id)
        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        # ── FTS mode ─────────────────────────────────────────────────────────
        if mode == "fts" or not mode:
            result = ctx.storage.search_notes_fts(
                q,
                vault_id=vault_id,
                skip=skip,
                limit=limit,
                folder=folder,
                tags=tags_list,
                date_from=date_from,
                date_to=date_to,
            )
            result["mode"] = "fts"
            return result

        # ── Semantic mode ─────────────────────────────────────────────────────
        if mode == "semantic":
            all_results = ctx.storage.search_notes(q, vault_id=vault_id, top_k=10000, search_type="semantic")
            all_results = [n for n in all_results if not getattr(n, "is_deleted", False)]

            if folder:
                all_results = [n for n in all_results if (getattr(n, "folder_id", "") or "").startswith(folder)]
            for t in tags_list:
                all_results = [
                    n for n in all_results if t.lower() in [x.lower() for x in (getattr(n, "tags", []) or [])]
                ]
            if date_from:
                dt_from = datetime.fromisoformat(date_from)
                all_results = [n for n in all_results if n.created_at and n.created_at >= dt_from]
            if date_to:
                dt_to = datetime.fromisoformat(date_to)
                all_results = [n for n in all_results if n.created_at and n.created_at <= dt_to]

            total = len(all_results)
            page = all_results[skip : skip + limit]
            return {
                "items": [_note_to_list_item(n).model_dump() for n in page],
                "total": total,
                "skip": skip,
                "limit": limit,
                "mode": "semantic",
            }

        # ── Hybrid mode ───────────────────────────────────────────────────────
        if mode == "hybrid":
            # FTS leg — fetch up to 200 candidates with snippets
            fts_result = ctx.storage.search_notes_fts(
                q,
                vault_id=vault_id,
                skip=0,
                limit=200,
                folder=folder,
                tags=tags_list,
                date_from=date_from,
                date_to=date_to,
            )
            fts_items = fts_result.get("items", [])

            # Semantic leg — fetch up to 200 candidates (no filters, applied post-merge)
            sem_ids: List[str] = []
            try:
                sem_notes = ctx.storage.search_notes(q, vault_id=vault_id, top_k=200, search_type="semantic")
                sem_ids = [n.id for n in sem_notes if not getattr(n, "is_deleted", False)]
            except Exception:
                pass  # semantic index may not be available

            # Merge: FTS weight 0.6, semantic weight 0.4, rank by position
            scores: Dict[str, dict] = {}
            for i, item in enumerate(fts_items):
                nid = item["id"]
                scores[nid] = {"item": item, "score": 0.6 / (i + 1)}

            for j, nid in enumerate(sem_ids):
                sem_score = 0.4 / (j + 1)
                if nid in scores:
                    scores[nid]["score"] += sem_score
                else:
                    note = ctx.storage.get_note_by_id(nid)
                    if note and not getattr(note, "is_deleted", False):
                        item_data = _note_to_list_item(note).model_dump()
                        item_data["snippet"] = ""
                        scores[nid] = {"item": item_data, "score": sem_score}

            merged = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
            all_items = [m["item"] for m in merged]
            total = len(all_items)
            page = all_items[skip : skip + limit]
            return {"items": page, "total": total, "skip": skip, "limit": limit, "mode": "hybrid"}

        # ── Unknown mode → fall back to FTS ──────────────────────────────────
        result = ctx.storage.search_notes_fts(
            q,
            vault_id=vault_id,
            skip=skip,
            limit=limit,
            folder=folder,
            tags=tags_list,
            date_from=date_from,
            date_to=date_to,
        )
        result["mode"] = mode
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/folders", response_model=List[FolderResponse])
async def list_folders(
    vault_id: Optional[str] = Query(None, description="Vault to list folders from"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List all folders."""
    try:
        _set_user_ctx(ctx, user)
        vault_id = _resolve_vault_id(ctx, user, vault_id)
        results = []

        # Primary: query folders stored in the SQLite database
        if hasattr(ctx.storage, "list_all_folders"):
            try:
                db_folders = ctx.storage.list_all_folders(vault_id=vault_id)
                for folder_obj in db_folders:
                    results.append(_folder_to_response(folder_obj, ctx, user))
            except Exception as exc:
                logger.warning("list_folders: DB folder enumeration failed: %s", exc)

        # Fallback: enumerate filesystem directories (legacy / Obsidian vaults)
        if not results:
            try:
                folder_paths = ctx.storage.list_folders(vault_id=vault_id) or []
                for fpath in folder_paths:
                    folder_obj = None
                    try:
                        folder_obj = ctx.folders.get_folder(fpath)
                    except Exception:
                        pass

                    if folder_obj:
                        results.append(_folder_to_response(folder_obj, ctx, user))
                    else:
                        name = fpath.rsplit("/", 1)[-1] if "/" in fpath else fpath
                        name = name.rsplit("\\", 1)[-1] if "\\" in name else name
                        meta = {}
                        try:
                            meta = ctx.storage.get_folder_metadata(fpath)
                        except Exception:
                            pass

                        results.append(
                            FolderResponse(
                                id=fpath,
                                name=name,
                                vault_id=vault_id,
                                parent_id=None,
                                description=None,
                                note_ids=[],
                                created_at=meta.get("created_at", datetime.utcnow()),
                                last_modified=meta.get("last_modified", datetime.utcnow()),
                            )
                        )
            except Exception as exc:
                logger.warning("list_folders: filesystem enumeration failed: %s", exc)

        return results
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list folders: {str(e)}",
        )


@router.get("/")
async def list_notes(
    folder: str = Query("", description="Folder path to list notes from"),
    tag: str = Query("", description="Filter by tag"),
    vault_id: Optional[str] = Query(None, description="Vault to list notes from"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List notes, optionally filtered by folder and/or tag. Returns paginated response."""
    try:
        _set_user_ctx(ctx, user)
        vault_id = _resolve_vault_id(ctx, user, vault_id)

        # Primary: query notes directly from the SQLite database.
        # This covers all notes created via the API (which have no .md file on disk).
        if hasattr(ctx.storage, "list_all_notes"):
            all_notes = ctx.storage.list_all_notes(folder=folder, tag=tag, vault_id=vault_id)
            # list_all_notes already filters by folder and tag; skip redundant filters.
            all_notes = [n for n in all_notes if not getattr(n, "is_deleted", False)]
        else:
            # Fallback for non-SQLite backends: file-based search
            all_notes = ctx.storage.search_notes("", vault_id=vault_id, top_k=10000)

            if folder:
                all_notes = [n for n in all_notes if getattr(n, "folder_id", None) == folder or n.id.startswith(folder)]
            if tag:
                all_notes = [n for n in all_notes if tag.lower() in [t.lower() for t in (getattr(n, "tags", []) or [])]]
            all_notes = [n for n in all_notes if not getattr(n, "is_deleted", False)]

        # Sort by last_modified descending
        all_notes.sort(key=lambda n: n.last_modified, reverse=True)

        total = len(all_notes)
        page = all_notes[skip : skip + limit]

        return {
            "items": [_note_to_list_item(n).model_dump() for n in page],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list notes: {str(e)}",
        )


@router.get("/{note_id}", response_model=NoteDetail)
async def get_note(
    note_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Get a specific note by ID with full content and metadata."""
    try:
        _set_user_ctx(ctx, user)
        note = _get_note_or_404(ctx, note_id)
        return _note_to_detail(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get note: {str(e)}",
        )


@router.post("/", response_model=NoteDetail)
async def create_note(
    req: CreateNoteRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a new note."""
    try:
        _set_user_ctx(ctx, user)
        vault_id = _resolve_vault_id(ctx, user, req.vault_id)
        note = ctx.notes.create_note(
            vault_id=vault_id,
            owner_id=user.id,
            title=req.title,
            content=req.content,
            folder_id=req.folder_id,
            tags=req.tags,
        )
        # Set meta if provided
        if req.meta:
            note.meta = req.meta
            ctx.notes.update_note(note, actor_id=user.id)
        await hub.publish_note_saved(vault_id, _note_to_detail(note).model_dump(mode="json"))
        ctx.analytics.track("note.created", user_id=user.id)
        return _note_to_detail(note)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create note: {str(e)}",
        )


@router.put("/{note_id}", response_model=NoteDetail)
async def update_note(
    note_id: str,
    req: UpdateNoteRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update an existing note — any combination of fields."""
    try:
        _set_user_ctx(ctx, user)
        note = _get_note_or_404(ctx, note_id)

        if req.title is not None:
            note.title = req.title
        if req.content is not None:
            note.content = req.content
        if req.tags is not None:
            note.tags = req.tags
        if req.folder_id != "__UNSET__":
            note.folder_id = req.folder_id
        if req.meta is not None:
            note.meta = {**(getattr(note, "meta", {}) or {}), **req.meta}
        if req.permissions is not None:
            note.permissions = _normalize_resource_permissions(req.permissions)
        if req.links is not None:
            note.links = req.links
        if req.group_id != "__UNSET__":
            previous_group_id = getattr(note, "group_id", None)
            next_group_id = req.group_id
            note.permissions = dict(getattr(note, "permissions", {}) or {})
            if next_group_id:
                group = ctx.groups.get_group(next_group_id)
                if not group or not getattr(group, "is_active", True):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Group not found",
                    )
                note.permissions[next_group_id] = "write"
            note.group_id = next_group_id
            if (
                previous_group_id
                and previous_group_id != next_group_id
            ):
                note.permissions.pop(previous_group_id, None)

        ctx.notes.update_note(note, actor_id=user.id)
        await hub.publish_note_saved(note.vault_id, _note_to_detail(note).model_dump(mode="json"))
        return _note_to_detail(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update note: {str(e)}",
        )


@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Delete a note."""
    try:
        _set_user_ctx(ctx, user)
        note = _get_note_or_404(ctx, note_id)

        is_admin = user.system_role in PLATFORM_ADMIN
        if note.owner_id != user.id and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        ctx.storage.soft_delete_note(note_id)
        ctx.analytics.track("note.deleted", user_id=user.id)
        return {"deleted": True, "path": note_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete note: {str(e)}",
        )


@router.post("/move")
async def move_note(
    req: MoveNoteRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Move a note to a different folder."""
    try:
        _set_user_ctx(ctx, user)
        note = _get_note_or_404(ctx, req.note_id)

        is_admin = user.system_role in PLATFORM_ADMIN
        if note.owner_id != user.id and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        note.folder_id = req.dest_folder_id
        ctx.notes.update_note(note, actor_id=user.id)
        return {"message": "Note moved successfully", "note_id": note.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Move failed: {str(e)}",
        )


# ============================================================================
# Tag endpoints (nested under /notes/{note_id}/tags)
# ============================================================================


@router.post("/{note_id}/tags", response_model=NoteDetail)
async def add_tag(
    note_id: str,
    req: TagRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Add a tag to a note."""
    try:
        _set_user_ctx(ctx, user)
        try:
            ctx.notes.add_tag(note_id, req.tag)
            note = ctx.notes.get_note(note_id)
        except Exception:
            # Fallback if NoteManager.add_tag doesn't exist
            note = _get_note_or_404(ctx, note_id)
            tags = list(set((getattr(note, "tags", []) or []) + [req.tag]))
            note.tags = tags
            ctx.notes.update_note(note, actor_id=user.id)

        return _note_to_detail(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add tag: {str(e)}",
        )


@router.delete("/{note_id}/tags/{tag}", response_model=NoteDetail)
async def remove_tag(
    note_id: str,
    tag: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Remove a tag from a note."""
    try:
        _set_user_ctx(ctx, user)
        try:
            ctx.notes.remove_tag(note_id, tag)
            note = ctx.notes.get_note(note_id)
        except Exception:
            note = _get_note_or_404(ctx, note_id)
            tags = [t for t in (getattr(note, "tags", []) or []) if t != tag]
            note.tags = tags
            ctx.notes.update_note(note, actor_id=user.id)

        return _note_to_detail(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove tag: {str(e)}",
        )


# ============================================================================
# Metadata endpoint
# ============================================================================


@router.put("/{note_id}/meta", response_model=NoteDetail)
async def update_meta(
    note_id: str,
    req: MetaUpdateRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update note metadata (merge into existing meta dict)."""
    try:
        _set_user_ctx(ctx, user)
        note = _get_note_or_404(ctx, note_id)
        existing_meta = getattr(note, "meta", {}) or {}
        # Merge: new values override, null values remove keys
        for k, v in req.meta.items():
            if v is None or v == "":
                existing_meta.pop(k, None)
            else:
                existing_meta[k] = v
        note.meta = existing_meta
        ctx.notes.update_note(note, actor_id=user.id)
        return _note_to_detail(note)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update metadata: {str(e)}",
        )


# ============================================================================
# Backlinks / relationship endpoints
# ============================================================================


@router.get("/{note_id}/backlinks")
async def get_note_backlinks(
    note_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return all wiki-link relationships involving this note.

    Each item has:
      direction   — "from" (this note links to other) | "to" (other links to this note)
      relation_type — always "wikilink" for now
      label       — display title of the linked entity
      other_entity_id   — the other note's id
      other_entity_type — "note"
    """
    try:
        _set_user_ctx(ctx, user)
        _get_note_or_404(ctx, note_id)

        results = []

        # Forward links: this note → targets
        forward_ids = []
        if hasattr(ctx.storage, "get_relationships"):
            try:
                forward_ids = ctx.storage.get_relationships(note_id) or []
            except Exception:
                pass

        for tid in forward_ids:
            other = ctx.notes.get_note(tid) if tid else None
            results.append({
                "direction": "from",
                "relation_type": "wikilink",
                "label": other.title if other else tid,
                "other_entity_id": tid,
                "other_entity_type": "note",
            })

        # Back links: sources → this note
        backward_ids = []
        if hasattr(ctx.storage, "get_backlinks"):
            try:
                backward_ids = ctx.storage.get_backlinks(note_id) or []
            except Exception:
                pass

        for sid in backward_ids:
            other = ctx.notes.get_note(sid) if sid else None
            results.append({
                "direction": "to",
                "relation_type": "wikilink",
                "label": other.title if other else sid,
                "other_entity_id": sid,
                "other_entity_type": "note",
            })

        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get backlinks: {str(e)}",
        )


@router.post("/{note_id}/relationships")
async def create_note_relationship(
    note_id: str,
    req: CreateRelationshipRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a wiki-link relationship from this note to target_id.

    Idempotent — safe to call multiple times for the same pair.
    """
    try:
        _set_user_ctx(ctx, user)
        _get_note_or_404(ctx, note_id)
        if hasattr(ctx.storage, "upsert_relationship"):
            ctx.storage.upsert_relationship(note_id, req.target_id)
        return {"created": True, "source_id": note_id, "target_id": req.target_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relationship: {str(e)}",
        )


# ============================================================================
# Folder endpoints (nested under /notes/folders)
# ============================================================================


@router.post("/folders", response_model=FolderResponse)
async def create_folder(
    req: CreateFolderRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a new folder."""
    try:
        _set_user_ctx(ctx, user)
        vault_id = _resolve_vault_id(ctx, user, req.vault_id)
        folder = ctx.folders.create_folder(
            vault_id=vault_id,
            name=req.name,
            owner_id=user.id,
            parent_id=req.parent_id,
        )
        return _folder_to_response(folder, ctx, user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create folder: {str(e)}",
        )


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: str,
    req: UpdateFolderRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Rename or update a folder."""
    try:
        _set_user_ctx(ctx, user)
        folder = ctx.folders.get_folder(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        if req.name is not None:
            folder.name = req.name
        if req.description is not None:
            folder.description = req.description

        ctx.folders.update_folder(folder)
        return _folder_to_response(folder, ctx, user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update folder: {str(e)}",
        )


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Delete a folder."""
    try:
        _set_user_ctx(ctx, user)
        folder = ctx.folders.get_folder(folder_id)
        if not folder:
            if ctx.storage.folder_exists(folder_id):
                ctx.storage.delete_folder(folder_id)
                return {"message": "Folder deleted successfully"}
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        is_admin = user.system_role in PLATFORM_ADMIN
        if folder.owner_id != user.id and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        ctx.folders.delete_folder(folder_id)
        return {"message": "Folder deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete folder: {str(e)}",
        )
