"""
Invite code management endpoints (admin only).

GET /invites — list all invite codes
POST /invites — generate a new invite code (ttl_days, max_uses)
POST /invites/generate — generate a new invite code (expires_hours)
DELETE /invites/{code} — revoke an invite code by code
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user, require_permission
from server.vault_access import is_vault_admin, resolve_vault

router = APIRouter()


# ============================================================================
# Request/Response models
# ============================================================================


class InviteListItem(BaseModel):
    """Invite code item in list response, including expiry, usage, and computed status."""

    id: str
    code: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    is_active: bool
    is_used: bool
    use_count: int
    max_uses: int
    used_by: str | None
    status: str


class GenerateInviteResponse(BaseModel):
    """Response body for invite generation endpoints."""

    code: str
    expires_at: datetime
    max_uses: int
    message: str


class GenerateInviteRequest(BaseModel):
    ttl_days: int = 7
    max_uses: int = 1
    vault_id: str | None = None


class GenerateInviteByHoursRequest(BaseModel):
    expires_hours: int | None = None
    vault_id: str | None = None


# ============================================================================
# Invite management endpoints
# ============================================================================


@router.get("/", response_model=List[InviteListItem])
async def list_invites(
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("admin"),
):
    """
    List all invite codes.

    Requires admin role. Shows active and inactive invites with usage information.
    """
    try:
        invite_list = ctx.storage.list_invites() or []

        return [
            InviteListItem(
                id=inv.id,
                code=inv.code,
                created_by=inv.created_by,
                created_at=inv.created_at,
                expires_at=inv.expires_at,
                is_active=inv.is_active,
                is_used=inv.use_count >= inv.max_uses,
                use_count=inv.use_count,
                used_by=inv.used_by,
                max_uses=inv.max_uses,
                status=inv.status,
            )
            for inv in invite_list
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list invites: {str(e)}",
        )


@router.post("/", response_model=GenerateInviteResponse)
async def generate_invite(
    body: GenerateInviteRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """
    Generate a new invite code.
    With vault_id: vault owner or vault-admin may generate.
    Without vault_id (platform invite): platform admin required.
    """
    if body.vault_id:
        vault = resolve_vault(ctx, user, body.vault_id)
        if not is_vault_admin(vault, user, ctx) and user.system_role not in PLATFORM_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vault admin or platform admin required to create vault invites",
            )
    elif user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin required to create platform invites",
        )
    try:
        invite = ctx.invites.generate_with_expiry(
            created_by_user_id=user.id,
            expiry_days=body.ttl_days,
            max_uses=body.max_uses,
        )

        return GenerateInviteResponse(
            code=invite.code,
            expires_at=invite.expires_at,
            max_uses=invite.max_uses,
            message=f"Invite code {invite.code} generated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate invite: {str(e)}",
        )


@router.post("/generate", response_model=GenerateInviteResponse)
async def generate_invite_by_hours(
    body: GenerateInviteByHoursRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """
    Generate a new invite code with an optional expires_hours param.
    With vault_id: vault owner or vault-admin may generate.
    Without vault_id (platform invite): platform admin required.
    """
    if body.vault_id:
        vault = resolve_vault(ctx, user, body.vault_id)
        if not is_vault_admin(vault, user, ctx) and user.system_role not in PLATFORM_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vault admin or platform admin required to create vault invites",
            )
    elif user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin required to create platform invites",
        )
    try:
        expiry_days = max(1, round(body.expires_hours / 24)) if body.expires_hours else 7
        invite = ctx.invites.generate_with_expiry(
            created_by_user_id=user.id,
            expiry_days=expiry_days,
            max_uses=1,
        )

        return GenerateInviteResponse(
            code=invite.code,
            expires_at=invite.expires_at,
            max_uses=invite.max_uses,
            message=f"Invite code {invite.code} generated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate invite: {str(e)}",
        )


@router.delete("/{code}")
async def revoke_invite(
    code: str,
    ctx: AppContext = Depends(get_ctx),
    admin: User = require_permission("admin"),
):
    """
    Revoke an invite code (mark as inactive). Accepts the invite code string.

    Requires admin role. The invite code can no longer be used after revocation.
    """
    try:
        invite = ctx.storage.get_invite_by_code(code)
        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found",
            )

        ctx.invites.revoke(invite.id)

        return {"message": "Invite revoked successfully", "code": code}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke invite: {str(e)}",
        )
