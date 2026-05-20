"""
Map endpoints.

GET /maps?vault_id=&type= — paginated list
GET /maps/{id}             — get map by id
POST /maps                 — create map
PUT /maps/{id}             — update map
DELETE /maps/{id}          — soft delete map
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.map import Map
from MythosEngine.models.user import User
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user
from server.vault_access import resolve_vault

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Request / Response models
# ============================================================================


class MarkerItem(BaseModel):
    id: str = ""
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    note_id: str = ""


class MapListItem(BaseModel):
    id: str
    campaign_id: str = ""  # preferred
    vault_id: str  # deprecated alias for campaign_id
    name: str
    map_type: str
    description: str
    image_path: str
    tags: List[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class MapDetail(BaseModel):
    id: str
    campaign_id: str = ""  # preferred
    vault_id: str  # deprecated alias for campaign_id
    owner_id: str
    name: str
    map_type: str
    description: str
    image_path: str
    markers: List[Dict[str, Any]]
    tags: List[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class CreateMapRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    campaign_id: Optional[str] = Field(default=None, max_length=100)
    vault_id: Optional[str] = Field(default=None, max_length=100)  # deprecated alias for campaign_id
    map_type: str = Field("region", max_length=50)
    description: str = Field("", max_length=10_000)
    image_path: str = Field("", max_length=1000)
    markers: List[MarkerItem] = Field(default_factory=list)
    tags: str = Field("", max_length=500)


class UpdateMapRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    map_type: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=10_000)
    image_path: Optional[str] = Field(None, max_length=1000)
    markers: Optional[List[MarkerItem]] = None
    tags: Optional[str] = Field(None, max_length=500)


# ============================================================================
# Helpers
# ============================================================================


def _map_to_list_item(m: Map) -> MapListItem:
    effective_id = getattr(m, "campaign_id", None) or getattr(m, "vault_id", "") or ""
    return MapListItem(
        id=m.id,
        campaign_id=effective_id,
        vault_id=effective_id,  # deprecated: mirrors campaign_id
        name=m.name,
        map_type=m.map_type,
        description=m.description or "",
        image_path=m.file_path,
        tags=m.tags or [],
        is_deleted=m.is_deleted,
        created_at=m.created_at,
        updated_at=m.last_modified,
    )


def _map_to_detail(m: Map) -> MapDetail:
    effective_id = getattr(m, "campaign_id", None) or getattr(m, "vault_id", "") or ""
    return MapDetail(
        id=m.id,
        campaign_id=effective_id,
        vault_id=effective_id,  # deprecated: mirrors campaign_id
        owner_id=m.owner_id,
        name=m.name,
        map_type=m.map_type,
        description=m.description or "",
        image_path=m.file_path,
        markers=m.markers or [],
        tags=m.tags or [],
        is_deleted=m.is_deleted,
        created_at=m.created_at,
        updated_at=m.last_modified,
    )


def _get_map_or_404(ctx, user: User, map_id: str) -> Map:
    m = ctx.maps.get_map(map_id)
    if not m or m.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Map not found")
    resolve_vault(ctx, user, getattr(m, "vault_id", None))
    return m


def _tags_str_to_list(tags: str) -> List[str]:
    return [t.strip() for t in tags.split(",") if t.strip()]


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/")
async def list_maps(
    campaign_id: Optional[str] = Query(None, description="Campaign ID (preferred)"),
    vault_id: Optional[str] = Query(None, description="Deprecated: use campaign_id instead"),
    type: Optional[str] = Query(None, description="Filter by map_type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    ctx=Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List maps for a campaign, optionally filtered by type.

    campaign_id is preferred; vault_id is a deprecated alias.
    """
    try:
        effective_id = campaign_id or (resolve_vault(ctx, user, vault_id).id if vault_id else None)
        all_maps = ctx.storage.list_maps(campaign_id=effective_id, map_type=type)
        all_maps.sort(key=lambda m: m.last_modified, reverse=True)
        total = len(all_maps)
        page = all_maps[skip : skip + limit]
        return {
            "items": [_map_to_list_item(m).model_dump() for m in page],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list maps: {e}")


@router.get("/{map_id}", response_model=MapDetail)
async def get_map(
    map_id: str,
    ctx=Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Get a map by ID."""
    try:
        return _map_to_detail(_get_map_or_404(ctx, user, map_id))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get map: {e}")


@router.post("/", response_model=MapDetail)
async def create_map(
    req: CreateMapRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a new map.

    campaign_id is preferred; vault_id is a deprecated alias.
    """
    try:
        effective_id = req.campaign_id or (resolve_vault(ctx, user, req.vault_id).id if req.vault_id else "default")
        m = ctx.maps.create_map(
            vault_id=effective_id,
            owner_id=user.id,
            name=req.name,
            file_path=req.image_path,
            description=req.description or None,
            tags=_tags_str_to_list(req.tags),
        )
        # Set extra fields not in create_map signature
        m.map_type = req.map_type
        m.markers = [marker.model_dump() for marker in req.markers]
        ctx.storage.save_map(m)
        ctx.analytics.track("map.created", user_id=user.id, data={"map_type": req.map_type})
        return _map_to_detail(m)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create map: {e}")


@router.put("/{map_id}", response_model=MapDetail)
async def update_map(
    map_id: str,
    req: UpdateMapRequest,
    ctx=Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update an existing map."""
    try:
        m = _get_map_or_404(ctx, user, map_id)

        is_admin = user.system_role in PLATFORM_ADMIN
        if m.owner_id != user.id and not is_admin:
            raise HTTPException(status_code=403, detail="Access denied")

        if req.name is not None:
            m.name = req.name
        if req.map_type is not None:
            m.map_type = req.map_type
        if req.description is not None:
            m.description = req.description
        if req.image_path is not None:
            m.file_path = req.image_path
        if req.markers is not None:
            m.markers = [marker.model_dump() for marker in req.markers]
        if req.tags is not None:
            m.tags = _tags_str_to_list(req.tags)

        ctx.maps.update_map(m)
        return _map_to_detail(m)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update map: {e}")


@router.delete("/{map_id}")
async def delete_map(
    map_id: str,
    ctx=Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Soft-delete a map."""
    try:
        m = _get_map_or_404(ctx, user, map_id)

        is_admin = user.system_role in PLATFORM_ADMIN
        if m.owner_id != user.id and not is_admin:
            raise HTTPException(status_code=403, detail="Access denied")

        ctx.storage.soft_delete_map(map_id)
        return {"deleted": True, "id": map_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete map: {e}")
