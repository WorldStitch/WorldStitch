"""
Vault email-invite endpoints.

POST   /vaults/{vault_id}/invites               — send email invite
GET    /vaults/{vault_id}/invites               — list pending/accepted invites
DELETE /vaults/{vault_id}/invites/{invite_id}   — revoke invite
POST   /vaults/{vault_id}/invites/{invite_id}/resend — resend email
GET    /invites/accept?token=TOKEN              — validate token (public)
POST   /invites/accept                          — accept invite (auth required)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user
from server.email import send_vault_invite_email
from server.vault_access import is_vault_admin, resolve_vault
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from WorldStitch.models.vault_invite import VaultInvite

router = APIRouter()


# ============================================================================
# Helpers
# ============================================================================


def _can_manage_invites(vault, user: User, ctx: AppContext) -> bool:
    if user.system_role in PLATFORM_ADMIN:
        return True
    return vault.owner_id == user.id or is_vault_admin(vault, user, ctx)


def _storage(ctx: AppContext):
    return ctx.storage


# ============================================================================
# Request / Response models
# ============================================================================


class SendInviteRequest(BaseModel):
    email: EmailStr


class VaultInviteItem(BaseModel):
    id: str
    vault_id: str
    email: str
    invited_by: str
    expires_at: datetime
    accepted: bool
    accepted_by: Optional[str]
    status: str
    created_at: Optional[datetime]
    token: Optional[str] = None  # included for pending invites so owner can copy the link


class AcceptTokenInfo(BaseModel):
    """Returned by GET /invites/accept — shows vault info before confirming."""

    vault_id: str
    vault_name: str
    invited_by_name: str
    email: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    token: str


# ============================================================================
# Vault-scoped endpoints  (mounted under /vaults/{vault_id}/invites)
# ============================================================================


@router.post("/vaults/{vault_id}/invites", status_code=201)
async def send_vault_invite(
    vault_id: str,
    body: SendInviteRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    if not _can_manage_invites(vault, user, ctx):
        raise HTTPException(status_code=403, detail="Only vault owners and admins can invite members")

    email = body.email.lower().strip()

    # If this email belongs to an existing user, check membership
    existing_user = None
    if hasattr(ctx.storage, "get_user_by_email"):
        existing_user = ctx.storage.get_user_by_email(email)
    if existing_user:
        if existing_user.id == vault.owner_id or existing_user.id in (vault.members or []):
            raise HTTPException(status_code=409, detail="Already a member of this vault")

    # Deduplicate pending invites to the same email
    existing = _storage(ctx).list_vault_invites(vault_id)
    for inv in existing:
        if inv.email == email and inv.status == "pending":
            raise HTTPException(status_code=409, detail="A pending invite for this email already exists")

    invite = VaultInvite(
        owner_id=user.id,
        vault_id=vault_id,
        email=email,
        token=secrets.token_urlsafe(32),
        invited_by=user.id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    _storage(ctx).save_vault_invite(invite)

    inviter_name = getattr(user, "username", None) or user.id
    send_vault_invite_email(
        to=email,
        vault_name=vault.name,
        inviter_name=inviter_name,
        token=invite.token,
    )

    return {"message": "Invite sent", "id": invite.id}


@router.get("/vaults/{vault_id}/invites", response_model=List[VaultInviteItem])
async def list_vault_invites(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    if not _can_manage_invites(vault, user, ctx):
        raise HTTPException(status_code=403, detail="Only vault owners and admins can view invites")

    invites = _storage(ctx).list_vault_invites(vault_id)
    return [
        VaultInviteItem(
            id=inv.id,
            vault_id=inv.vault_id,
            email=inv.email,
            invited_by=inv.invited_by,
            expires_at=inv.expires_at,
            accepted=inv.accepted,
            accepted_by=inv.accepted_by,
            status=inv.status,
            created_at=inv.created_at,
            token=inv.token if inv.status == "pending" else None,
        )
        for inv in invites
    ]


@router.delete("/vaults/{vault_id}/invites/{invite_id}", status_code=204)
async def revoke_vault_invite(
    vault_id: str,
    invite_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    if not _can_manage_invites(vault, user, ctx):
        raise HTTPException(status_code=403, detail="Only vault owners and admins can revoke invites")

    invite = _storage(ctx).get_vault_invite_by_id(invite_id)
    if not invite or invite.vault_id != vault_id:
        raise HTTPException(status_code=404, detail="Invite not found")

    invite.is_active = False
    _storage(ctx).save_vault_invite(invite)


@router.post("/vaults/{vault_id}/invites/{invite_id}/resend", status_code=200)
async def resend_vault_invite(
    vault_id: str,
    invite_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    if not _can_manage_invites(vault, user, ctx):
        raise HTTPException(status_code=403, detail="Only vault owners and admins can resend invites")

    invite = _storage(ctx).get_vault_invite_by_id(invite_id)
    if not invite or invite.vault_id != vault_id:
        raise HTTPException(status_code=404, detail="Invite not found")
    if not invite.is_active:
        raise HTTPException(status_code=409, detail="Invite has been revoked")
    if invite.accepted:
        raise HTTPException(status_code=409, detail="Invite already accepted")

    # Refresh expiry
    invite.expires_at = datetime.utcnow() + timedelta(days=7)
    _storage(ctx).save_vault_invite(invite)

    inviter_name = getattr(user, "username", None) or user.id
    send_vault_invite_email(
        to=invite.email,
        vault_name=vault.name,
        inviter_name=inviter_name,
        token=invite.token,
    )
    return {"message": "Invite resent"}


# ============================================================================
# Token-based accept endpoints  (mounted at root, no vault_id in path)
# ============================================================================


@router.get("/invites/accept", response_model=AcceptTokenInfo)
async def validate_invite_token(
    token: str = Query(...),
    ctx: AppContext = Depends(get_ctx),
):
    """Public endpoint — validates a token and returns vault info so the UI
    can show 'You've been invited to join <VaultName>' before the user logs in."""
    invite = _storage(ctx).get_vault_invite_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if not invite.is_active:
        raise HTTPException(status_code=410, detail="Invite has been revoked")
    if invite.accepted:
        raise HTTPException(status_code=409, detail="Invite already accepted")
    if datetime.utcnow() >= invite.expires_at:
        raise HTTPException(status_code=410, detail="Invite has expired")

    vault = None
    if hasattr(ctx.storage, "get_vault_by_id"):
        vault = ctx.storage.get_vault_by_id(invite.vault_id)
    if not vault:
        raise HTTPException(status_code=404, detail="Vault not found")

    inviter_name = invite.invited_by
    inviter = ctx.users.get_user(invite.invited_by)
    if inviter:
        inviter_name = getattr(inviter, "username", None) or invite.invited_by

    return AcceptTokenInfo(
        vault_id=invite.vault_id,
        vault_name=vault.name,
        invited_by_name=inviter_name,
        email=invite.email,
        expires_at=invite.expires_at,
    )


@router.post("/invites/accept")
async def accept_invite(
    body: AcceptInviteRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Accept a vault invite. Adds the current user as a vault member."""
    invite = _storage(ctx).get_vault_invite_by_token(body.token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if not invite.is_active:
        raise HTTPException(status_code=410, detail="Invite has been revoked")
    if invite.accepted:
        raise HTTPException(status_code=409, detail="Invite already accepted")
    if datetime.utcnow() >= invite.expires_at:
        raise HTTPException(status_code=410, detail="Invite has expired")

    vault = None
    if hasattr(ctx.storage, "get_vault_by_id"):
        vault = ctx.storage.get_vault_by_id(invite.vault_id)
    if not vault:
        raise HTTPException(status_code=404, detail="Vault not found")

    if vault.owner_id == user.id or user.id in (vault.members or []):
        raise HTTPException(status_code=409, detail="Already a member of this vault")

    ctx.vaults.add_member(invite.vault_id, user.id)

    invite.accepted = True
    invite.accepted_by = user.id
    _storage(ctx).save_vault_invite(invite)

    return {"message": "Welcome to the vault!", "vault_id": invite.vault_id, "vault_name": vault.name}
