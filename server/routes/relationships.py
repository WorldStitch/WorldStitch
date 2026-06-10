"""
Relationship (edge) endpoints.

GET  /relationships?vault_id=&entity_id=   list relationships (entity_id optional filter)
POST /relationships                         create a relationship
GET  /relationships/types                  return RELATIONSHIP_TYPES list (no auth)
GET  /relationships/{id}                   get one relationship
PUT  /relationships/{id}                   update label, weight, or type
DELETE /relationships/{id}                 soft delete
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from server.context import AppContext
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user
from server.vault_access import resolve_vault
from WorldStitch.models.relationship import Relationship
from WorldStitch.models.relationship_types import RELATIONSHIP_TYPES
from WorldStitch.models.user import User

router = APIRouter()


# ============================================================================
# Request / Response models
# ============================================================================


class RelationshipDetail(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship_type: str
    direction: str
    label: Optional[str] = None
    weight: float
    owner_id: str
    vault_id: str
    meta: Dict[str, str] = {}
    created_at: datetime
    last_modified: datetime


class CreateRelationshipRequest(BaseModel):
    source_id: str = Field(..., max_length=100)
    target_id: str = Field(..., max_length=100)
    relationship_type: str = Field(..., max_length=200)
    direction: str = Field("bidirectional", pattern="^(unidirectional|bidirectional)$")
    label: Optional[str] = Field(None, max_length=500)
    weight: float = Field(1.0, ge=0.0, le=1.0)
    vault_id: Optional[str] = Field(None, max_length=100)
    meta: Dict[str, str] = {}


class UpdateRelationshipRequest(BaseModel):
    relationship_type: Optional[str] = Field(None, max_length=200)
    direction: Optional[str] = Field(None, pattern="^(unidirectional|bidirectional)$")
    label: Optional[str] = Field(None, max_length=500)
    weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    meta: Optional[Dict[str, str]] = None


# ============================================================================
# Helpers
# ============================================================================


def _rel_to_detail(rel: Relationship) -> RelationshipDetail:
    return RelationshipDetail(
        id=rel.id,
        source_id=rel.source_id,
        target_id=rel.target_id,
        relationship_type=rel.relationship_type,
        direction=rel.direction,
        label=rel.label,
        weight=rel.weight,
        owner_id=rel.owner_id,
        vault_id=rel.vault_id,
        meta=rel.meta or {},
        created_at=rel.created_at,
        last_modified=rel.last_modified,
    )


# ============================================================================
# Routes
# ============================================================================


@router.get("/types")
async def list_relationship_types() -> List[Dict[str, Any]]:
    """Return the full predefined relationship type registry. No auth required."""
    return RELATIONSHIP_TYPES


@router.get("/")
async def list_relationships(
    vault_id: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List relationships for a vault, optionally filtered to a specific entity."""
    vault = await resolve_vault(ctx, user, vault_id)

    if entity_id:
        rels = await ctx.storage.list_relationships_for_entity(entity_id, vault.id)
    else:
        rels = await ctx.storage.list_relationships(vault.id)

    return [_rel_to_detail(r).model_dump() for r in rels]


@router.post("/", response_model=RelationshipDetail)
async def create_relationship(
    req: CreateRelationshipRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a new typed relationship edge."""
    vault = await resolve_vault(ctx, user, req.vault_id)

    rel = Relationship(
        source_id=req.source_id,
        target_id=req.target_id,
        relationship_type=req.relationship_type,
        direction=req.direction,
        label=req.label,
        weight=req.weight,
        owner_id=user.id,
        vault_id=vault.id,
        meta=req.meta or {},
    )
    created = await ctx.storage.create_relationship(rel)
    return _rel_to_detail(created)


@router.get("/{rel_id}", response_model=RelationshipDetail)
async def get_relationship(
    rel_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Get a single relationship by ID."""
    rel = await ctx.storage.get_relationship(rel_id)
    if not rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")

    await resolve_vault(ctx, user, rel.vault_id)
    return _rel_to_detail(rel)


@router.put("/{rel_id}", response_model=RelationshipDetail)
async def update_relationship(
    rel_id: str,
    req: UpdateRelationshipRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update label, weight, type, or direction on a relationship."""
    rel = await ctx.storage.get_relationship(rel_id)
    if not rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")

    await resolve_vault(ctx, user, rel.vault_id)

    is_admin = user.system_role in PLATFORM_ADMIN
    if rel.owner_id != user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    updates: Dict[str, Any] = {}
    if req.relationship_type is not None:
        updates["relationship_type"] = req.relationship_type
    if req.direction is not None:
        updates["direction"] = req.direction
    if req.label is not None:
        updates["label"] = req.label
    if req.weight is not None:
        updates["weight"] = req.weight
    if req.meta is not None:
        updates["meta"] = req.meta

    updated = await ctx.storage.update_relationship(rel_id, updates)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return _rel_to_detail(updated)


@router.delete("/{rel_id}")
async def delete_relationship(
    rel_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Soft-delete a relationship."""
    rel = await ctx.storage.get_relationship(rel_id)
    if not rel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")

    await resolve_vault(ctx, user, rel.vault_id)

    is_admin = user.system_role in PLATFORM_ADMIN
    if rel.owner_id != user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await ctx.storage.delete_relationship(rel_id)
    return {"deleted": True, "id": rel_id}
