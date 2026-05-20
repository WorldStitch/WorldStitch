"""
Campaign CRUD endpoints.

GET  /campaigns?group_id=               — list campaigns for a group
GET  /campaigns/{id}                    — get single campaign
POST /campaigns                         — create campaign
DELETE /campaigns/{id}                  — soft-delete campaign

GET  /campaigns/{id}/members            — list members
POST /campaigns/{id}/members            — add / update member role
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────


class CampaignResponse(BaseModel):
    id: str
    group_id: str
    name: str
    slug: str
    description: str = ""
    system: str = ""
    status: str = "active"
    created_by_user_id: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateCampaignRequest(BaseModel):
    group_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=300)
    description: str = Field("", max_length=5000)
    system: str = Field("", max_length=200)


class CampaignMemberRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field("player", pattern="^(gm|player|observer)$")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_response(row: dict) -> CampaignResponse:
    return CampaignResponse(
        id=row["id"],
        group_id=row["group_id"],
        name=row["name"],
        slug=row["slug"],
        description=row.get("description") or "",
        system=row.get("system") or "",
        status=row.get("status") or "active",
        created_by_user_id=row.get("created_by_user_id") or "",
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _get_campaign_or_404(ctx: AppContext, campaign_id: str) -> dict:
    campaign = ctx.storage.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/", response_model=List[CampaignResponse])
async def list_campaigns(
    group_id: str = Query(..., description="Group ID to list campaigns for"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List all active campaigns for a group."""
    try:
        rows = ctx.storage.list_campaigns_for_group(group_id)
        return [_row_to_response(r) for r in rows]
    except Exception as exc:
        logger.exception("list_campaigns failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Get a single campaign by ID."""
    return _row_to_response(_get_campaign_or_404(ctx, campaign_id))


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    req: CreateCampaignRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create a new campaign inside a group."""
    try:
        row = ctx.storage.create_campaign(
            group_id=req.group_id,
            owner_user_id=user.id,
            name=req.name,
            description=req.description,
            system=req.system,
        )
        # Auto-add creator as GM
        ctx.storage.add_campaign_member(row["id"], user.id, role="gm")
        return _row_to_response(row)
    except Exception as exc:
        logger.exception("create_campaign failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Soft-delete a campaign (sets deleted_at)."""
    campaign = _get_campaign_or_404(ctx, campaign_id)
    is_admin = user.system_role in PLATFORM_ADMIN
    if campaign.get("created_by_user_id") != user.id and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        from sqlalchemy import text as _text
        with ctx.storage.engine.connect() as conn:
            conn.execute(
                _text("UPDATE campaigns SET deleted_at = CURRENT_TIMESTAMP WHERE id = :id"),
                {"id": campaign_id},
            )
            conn.commit()
    except Exception as exc:
        logger.exception("delete_campaign failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Member sub-resource ───────────────────────────────────────────────────────


@router.get("/{campaign_id}/members")
async def list_campaign_members(
    campaign_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List all members of a campaign."""
    _get_campaign_or_404(ctx, campaign_id)
    try:
        return ctx.storage.list_campaign_members(campaign_id)
    except Exception as exc:
        logger.exception("list_campaign_members failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{campaign_id}/members", status_code=status.HTTP_201_CREATED)
async def add_campaign_member(
    campaign_id: str,
    req: CampaignMemberRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Add a user to a campaign with the given role."""
    _get_campaign_or_404(ctx, campaign_id)
    is_admin = user.system_role in PLATFORM_ADMIN
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform admins can add campaign members")
    try:
        return ctx.storage.add_campaign_member(campaign_id, req.user_id, req.role)
    except Exception as exc:
        logger.exception("add_campaign_member failed")
        raise HTTPException(status_code=500, detail=str(exc))
