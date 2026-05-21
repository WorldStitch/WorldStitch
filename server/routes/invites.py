"""
Invite code management endpoints.

GET /invites — list invite codes (platform admin: all; vault owner/admin: own)
POST /invites — generate a new invite code (ttl_days, max_uses)
POST /invites/generate — generate a new invite code (expires_hours)
DELETE /invites/{code} — revoke an invite code by code

Permission model:
  - Platform admins (system_role in {owner, admin}): full access to all invites
  - Vault owners / vault admins: can create invites and view/revoke their own
  - Regular users: no access
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user
from server.vault_access import list_accessible_vaults, is_vault_admin

router = APIRouter()


# ============================================================================
# Permission helper
# ============================================================================


def _can_create_invites(user: User, ctx: AppContext) -> bool:
    """
    Return True if the user is allowed to generate invite codes.
    Permitted for:
      - Platform admins (owner / admin system_role)
      - Vault owners (owns at least one vault)
      - Vault admins (is admin on at least one vault they can access)
    """
    if user.system_role in PLATFORM_ADMIN:
        return True
    try:
        vaults = list_accessible_vaults(ctx, user)
        for vault in vaults:
            if vault.owner_id == user.id or is_vault_admin(vault, user, ctx):
                return True
    except Exception:
        pass
    return False


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


class GenerateInviteByHoursRequest(BaseModel):
    expires_hours: int | None = None


# ============================================================================
# Invite management endpoints
# ============================================================================


@router.get("/", response_model=List[InviteListItem])
async def list_invites(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """
    List invite codes.
    Platform admins see all invites. Vault owners/admins see only invites they created.
    """
    if not _can_create_invites(user, ctx):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view invites")
    try:
        invite_list = ctx.storage.list_invites() or []
        # Non-platform-admins see only invites they created
        if user.system_role not in PLATFORM_ADMIN:
            invite_list = [inv for inv in invite_list if inv.created_by == user.id]

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
    except HTTPException:
        raise
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
    Generate a new invite code with ttl_days and max_uses.
    Requires platform admin, vault owner, or vault admin.
    """
    if not _can_create_invites(user, ctx):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform admins and vault owners/admins can generate invites")
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
    Requires platform admin, vault owner, or vault admin.
    """
    if not _can_create_invites(user, ctx):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only platform admins and vault owners/admins can generate invites")
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
    user: User = Depends(get_current_user),
):
    """
    Revoke an invite code (mark as inactive).
    Platform admins can revoke any invite. Vault owners/admins can revoke invites they created.
    """
    if not _can_create_invites(user, ctx):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to revoke invites")
    try:
        invite = ctx.storage.get_invite_by_code(code)
        if not invite:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invite not found",
            )

        # Non-platform-admins can only revoke invites they created
        if user.system_role not in PLATFORM_ADMIN and invite.created_by != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only revoke invites you created",
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
