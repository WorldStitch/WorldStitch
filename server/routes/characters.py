"""
Character CRUD endpoints.

GET  /characters?vault_id=&type=  — paginated list {items, total}
GET  /characters/{id}             — single character or 404
POST /characters                  — create
PUT  /characters/{id}             — partial update
DELETE /characters/{id}           — soft delete
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from server.deps import get_ctx, get_current_user
from server.embeddings import embed_entity, get_api_key_for_vault
from server.vault_access import resolve_vault
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.character import Character
from WorldStitch.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response / request models ─────────────────────────────────────────────────


class CharacterResponse(BaseModel):
    id: str
    campaign_id: str = ""  # preferred
    vault_id: str  # deprecated alias for campaign_id
    name: str
    char_type: str
    race: str = ""
    char_class: str = ""
    level: int = 1
    stats: Dict[str, Any] = {}
    ai_memory: str = ""
    note_ids: List[str] = []
    backstory: str = ""
    is_deleted: bool = False
    owner_id: str = ""
    created_at: datetime
    updated_at: datetime


class CreateCharacterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    char_type: str = Field("npc", pattern="^(player|npc)$")
    race: str = Field("", max_length=100)
    char_class: str = Field("", max_length=100)
    level: int = Field(1, ge=1, le=30)
    stats: Dict[str, Any] = {}
    backstory: str = Field("", max_length=10_000)
    ai_memory: str = Field("", max_length=50_000)
    note_ids: List[str] = []
    campaign_id: Optional[str] = Field(default=None, max_length=100)
    vault_id: Optional[str] = Field(default=None, max_length=100)  # deprecated alias for campaign_id


class UpdateCharacterRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    char_type: Optional[str] = Field(None, pattern="^(player|npc)$")
    race: Optional[str] = Field(None, max_length=100)
    char_class: Optional[str] = Field(None, max_length=100)
    level: Optional[int] = Field(None, ge=1, le=30)
    stats: Optional[Dict[str, Any]] = None
    backstory: Optional[str] = Field(None, max_length=10_000)
    ai_memory: Optional[str] = Field(None, max_length=50_000)
    note_ids: Optional[List[str]] = None


# ── Helper ────────────────────────────────────────────────────────────────────


def _to_response(char: Character) -> CharacterResponse:
    meta = getattr(char, "meta", {}) or {}
    effective_id = getattr(char, "campaign_id", None) or getattr(char, "vault_id", "default") or "default"
    return CharacterResponse(
        id=char.id,
        campaign_id=effective_id,
        vault_id=effective_id,  # deprecated: mirrors campaign_id
        name=char.name,
        char_type="npc" if getattr(char, "is_npc", False) else "player",
        race=str(meta.get("race", "")),
        char_class=str(meta.get("class", "")),
        level=int(meta.get("level", 1)),
        stats=getattr(char, "stats", {}) or {},
        ai_memory=getattr(char, "ai_memory", "") or "",
        note_ids=getattr(char, "note_ids", []) or [],
        backstory=getattr(char, "description", "") or "",
        is_deleted=getattr(char, "is_deleted", False),
        owner_id=getattr(char, "owner_id", ""),
        created_at=char.created_at,
        updated_at=char.last_modified,
    )


def _get_character_or_404(ctx: AppContext, user: User, char_id: str) -> Character:
    char = ctx.storage.get_character_by_id(char_id)
    if not char or getattr(char, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    resolve_vault(ctx, user, getattr(char, "vault_id", None))
    return char


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/")
async def list_characters(
    campaign_id: Optional[str] = Query(None, description="Campaign ID (preferred)"),
    vault_id: Optional[str] = Query(None, description="Deprecated: use campaign_id instead"),
    type: Optional[str] = Query(None, description="player or npc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List characters filtered by campaign and optionally type.

    campaign_id is preferred; vault_id is a deprecated alias.
    """
    try:
        # If no campaign_id, fall back to vault resolution for backward compat
        effective_id = campaign_id or (resolve_vault(ctx, user, vault_id).id if vault_id else None)
        all_chars = ctx.storage.list_characters(campaign_id=effective_id, char_type=type)
        total = len(all_chars)
        page = all_chars[skip : skip + limit]
        return {"items": [_to_response(c).model_dump() for c in page], "total": total}
    except Exception as exc:
        logger.exception("list_characters failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{char_id}", response_model=CharacterResponse)
async def get_character(
    char_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Get a single character by ID."""
    return _to_response(_get_character_or_404(ctx, user, char_id))


@router.post("/", response_model=CharacterResponse)
async def create_character(
    req: CreateCharacterRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a new character.

    campaign_id is preferred; vault_id is a deprecated alias.
    """
    try:
        # campaign_id takes precedence; vault_id is a deprecated alias
        effective_id = req.campaign_id or (resolve_vault(ctx, user, req.vault_id).id if req.vault_id else "default")
        char = Character(
            id=str(uuid.uuid4()),
            vault_id=effective_id,  # kept for backward compat on the model
            campaign_id=effective_id,
            owner_id=user.id,
            name=req.name,
            description=req.backstory or None,
            is_npc=(req.char_type == "npc"),
            stats=req.stats or {},
            note_ids=req.note_ids or [],
            meta={"race": req.race, "class": req.char_class, "level": req.level},
            ai_memory=req.ai_memory or None,
        )
        ctx.storage.save_character(char)
        ctx.analytics.track("character.created", user_id=user.id, data={"char_type": req.char_type})
        # Fire-and-forget embedding
        _embed_key = get_api_key_for_vault(effective_id, user, ctx)
        _embed_engine = getattr(ctx.storage, "engine", None)
        if _embed_key and _embed_engine:
            asyncio.create_task(
                embed_entity(
                    "characters",
                    char.id,
                    f"{char.name}\n\n{char.description or ''}",
                    _embed_key,
                    _embed_engine,
                )
            )
        return _to_response(char)
    except Exception as exc:
        logger.exception("create_character failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{char_id}", response_model=CharacterResponse)
async def update_character(
    char_id: str,
    req: UpdateCharacterRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Partially update a character."""
    char = _get_character_or_404(ctx, user, char_id)

    try:
        if req.name is not None:
            char.name = req.name
        if req.char_type is not None:
            char.is_npc = req.char_type == "npc"
        if req.backstory is not None:
            char.description = req.backstory
        if req.stats is not None:
            char.stats = req.stats
        if req.ai_memory is not None:
            char.ai_memory = req.ai_memory
        if req.note_ids is not None:
            char.note_ids = req.note_ids

        meta = dict(getattr(char, "meta", {}) or {})
        if req.race is not None:
            meta["race"] = req.race
        if req.char_class is not None:
            meta["class"] = req.char_class
        if req.level is not None:
            meta["level"] = req.level
        char.meta = meta
        char.last_modified = datetime.utcnow()

        ctx.storage.save_character(char)
        # Fire-and-forget re-embedding
        _vault_id = getattr(char, "vault_id", None) or getattr(char, "campaign_id", None) or ""
        _embed_key = get_api_key_for_vault(_vault_id, user, ctx)
        _embed_engine = getattr(ctx.storage, "engine", None)
        if _embed_key and _embed_engine:
            asyncio.create_task(
                embed_entity(
                    "characters",
                    char.id,
                    f"{char.name}\n\n{getattr(char, 'description', '') or ''}",
                    _embed_key,
                    _embed_engine,
                )
            )
        return _to_response(char)
    except Exception as exc:
        logger.exception("update_character failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{char_id}")
async def delete_character(
    char_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Soft-delete a character."""
    _get_character_or_404(ctx, user, char_id)
    ctx.storage.soft_delete_character(char_id)
    ctx.analytics.track("character.deleted", user_id=user.id)
    return {"deleted": True, "id": char_id}
