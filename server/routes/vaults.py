from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from server.context import AppContext
from server.deps import PLATFORM_ADMIN, VAULT_ADMIN_AND_ABOVE, VAULT_ROLES, get_ctx, get_current_user
from server.storage import Actor
from server.vault_access import list_accessible_vaults, resolve_vault
from WorldStitch.models.user import User
from WorldStitch.models.vault import Vault

logger = logging.getLogger(__name__)

router = APIRouter()


class VaultResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_id: str
    members: List[str] = []
    permissions: Dict[str, str] = {}
    is_active: bool
    settings: Dict[str, str] = {}
    vault_type: str = "worldbuilding"
    record_version: int = 1
    created_at: Optional[datetime] = None
    ai_key_shared: bool = False
    has_ai_key: bool = False


class CreateVaultRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    description: Optional[str] = None
    vault_type: Optional[str] = None


class UpdateVaultRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=64)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    vault_type: Optional[str] = None
    shared_group_id: Optional[str] = None
    backup_cron: Optional[str] = None


class VaultAiKeyRequest(BaseModel):
    api_key: str


class VaultAiSharingRequest(BaseModel):
    shared: bool


class VaultSearchItem(BaseModel):
    id: str
    title: str
    snippet: str = ""
    score: float = 0.0
    folder_id: Optional[str] = None
    updated_at: Optional[datetime] = None


class VaultSearchResponse(BaseModel):
    items: List[VaultSearchItem]
    total: int
    skip: int
    limit: int


async def _to_response(vault: Vault, ctx: AppContext) -> VaultResponse:
    has_key = False
    try:
        has_key = bool(await ctx.storage.get_vault_ai_key(vault.id))
    except Exception:
        logger.debug("_to_response: could not check AI key for vault %s", vault.id)
    return VaultResponse(
        **{k: v for k, v in vault.model_dump().items() if k in VaultResponse.model_fields},
        has_ai_key=has_key,
    )


@router.get("/", response_model=List[VaultResponse])
async def list_vaults(
    all: bool = Query(False, description="Platform admins only: return all vaults (explore/analytics mode)"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vaults = await list_accessible_vaults(ctx, user, all_vaults=all)
    return [await _to_response(vault, ctx) for vault in vaults]


@router.get("/{vault_id}", response_model=VaultResponse)
async def get_vault(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = await resolve_vault(ctx, user, vault_id)
    return await _to_response(vault, ctx)


@router.post("/", response_model=VaultResponse, status_code=status.HTTP_201_CREATED)
async def create_vault(
    body: CreateVaultRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = await ctx.storage.create_vault(
        name=body.name,
        owner_id=user.id,
        description=body.description,
        vault_type=body.vault_type,
    )
    # Insert the creator as vault owner in vault_members
    try:
        await ctx.storage.add_vault_member(vault.id, user.id, "owner")
    except Exception:
        logger.warning("create_vault: failed to insert vault_member for owner", exc_info=True)
    return await _to_response(vault, ctx)


@router.put("/{vault_id}", response_model=VaultResponse)
async def update_vault(
    vault_id: str,
    body: UpdateVaultRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner or an admin can update this vault")
    if body.name is not None:
        vault.name = body.name
    if body.description is not None:
        vault.description = body.description
    if body.is_active is not None:
        vault.is_active = body.is_active
    if body.vault_type is not None:
        vault.vault_type = body.vault_type
    if body.shared_group_id:
        group = await ctx.storage.get_group_by_id(body.shared_group_id)
        if not group or not getattr(group, "is_active", True):
            raise HTTPException(status_code=404, detail="Group not found")
        vault.permissions = dict(getattr(vault, "permissions", {}) or {})
        vault.permissions[body.shared_group_id] = "write"
        if vault.id not in (group.vault_ids or []):
            group.vault_ids.append(vault.id)
            await ctx.storage.update_group(group)
    if body.backup_cron:
        await ctx.storage.schedule_vault_backup(vault.id, body.backup_cron)
        vault.settings["backup_cron"] = body.backup_cron
    await ctx.storage.update_vault(vault)
    return await _to_response(vault, ctx)


@router.delete("/{vault_id}")
async def delete_vault(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete this vault")
    await ctx.storage.delete_vault(vault_id, actor_id=user.id)
    return {"deleted": True, "id": vault_id}


@router.get("/{vault_id}/export")
async def export_vault(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    await resolve_vault(ctx, user, vault_id)
    content = await ctx.storage.export_vault_zip(Actor.from_user(user), vault_id)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{vault_id}.zip"'},
    )


@router.post("/import", response_model=VaultResponse, status_code=status.HTTP_201_CREATED)
async def import_vault(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    payload = await file.read()
    vault = await ctx.storage.import_vault_zip(payload, owner_id=user.id, name=name)
    return await _to_response(vault, ctx)


@router.put("/{vault_id}/backup")
async def configure_backup(
    vault_id: str,
    cron: str = Query(..., min_length=5),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    await resolve_vault(ctx, user, vault_id)
    return await ctx.storage.schedule_vault_backup(vault_id, cron)


# ── Vault AI key management ───────────────────────────────────────────────────


@router.get("/{vault_id}/ai-key/status")
async def get_vault_ai_key_status(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return whether this vault has an AI key set, and whether sharing is enabled."""
    vault = await resolve_vault(ctx, user, vault_id)
    has_key = False
    try:
        has_key = bool(await ctx.storage.get_vault_ai_key(vault_id))
    except Exception:
        logger.debug("get_vault_ai_key_status: could not check AI key for vault %s", vault_id)
    return {
        "has_ai_key": has_key,
        "ai_key_shared": getattr(vault, "ai_key_shared", False),
        "is_owner": vault.owner_id == user.id,
    }


@router.post("/{vault_id}/ai-key", status_code=204)
async def save_vault_ai_key(
    vault_id: str,
    body: VaultAiKeyRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Save an encrypted AI key for this vault. Only the vault owner or platform admin may do this."""
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the vault owner can set an AI key.")
    if not body.api_key.startswith("sk-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="API key must start with 'sk-'.",
        )
    await ctx.storage.save_vault_ai_key(vault_id, body.api_key)


@router.delete("/{vault_id}/ai-key", status_code=204)
async def remove_vault_ai_key(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Remove this vault's AI key."""
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the vault owner can remove the AI key.")
    await ctx.storage.remove_vault_ai_key(vault_id)


@router.put("/{vault_id}/ai-key/sharing", status_code=204)
async def set_vault_ai_sharing(
    vault_id: str,
    body: VaultAiSharingRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Toggle whether vault members may use this vault's AI key."""
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the vault owner can change key sharing.")
    vault.ai_key_shared = body.shared
    await ctx.storage.update_vault(vault)
    await ctx.storage.set_vault_ai_sharing(vault_id, body.shared)


@router.get("/{vault_id}/search", response_model=VaultSearchResponse)
async def search_vault_notes(
    vault_id: str,
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Full-text search across all notes in a vault by content and title."""
    vault = await resolve_vault(ctx, user, vault_id)
    return await ctx.storage.search_notes_fts(q, vault_id=vault.id, skip=offset, limit=limit)


# ── Vault member management ───────────────────────────────────────────────────


class AddMemberRequest(BaseModel):
    user_id: str
    vault_role: str = Field("viewer", description="owner/admin/editor/viewer/player")


class UpdateMemberRoleRequest(BaseModel):
    vault_role: str = Field(..., description="owner/admin/editor/viewer/player")


async def _require_vault_admin(vault: Vault, user: User, ctx: AppContext) -> None:
    """Raise 403 unless the user is vault owner/admin or platform admin."""
    from server.vault_access import is_vault_admin

    if not await is_vault_admin(vault, user, ctx) and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Vault admin required.")


@router.get("/{vault_id}/members")
async def list_vault_members(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List all members of a vault with their roles."""
    await resolve_vault(ctx, user, vault_id)
    return await ctx.storage.list_vault_members(vault_id)


@router.post("/{vault_id}/members", status_code=status.HTTP_201_CREATED)
async def add_vault_member(
    vault_id: str,
    body: AddMemberRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Add or update a vault member. Requires vault admin or platform admin."""
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Vault admin required to manage members.")
    if body.vault_role not in VAULT_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid vault_role. Must be one of: {', '.join(VAULT_ROLES)}",
        )
    await ctx.storage.add_vault_member(vault_id, body.user_id, body.vault_role, invited_by=user.id)
    return {"added": True, "vault_id": vault_id, "user_id": body.user_id, "vault_role": body.vault_role}


@router.put("/{vault_id}/members/{member_user_id}")
async def update_vault_member_role(
    vault_id: str,
    member_user_id: str,
    body: UpdateMemberRoleRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Change a vault member's role. Requires vault admin or platform admin."""
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Vault admin required to manage members.")
    if body.vault_role not in VAULT_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid vault_role. Must be one of: {', '.join(VAULT_ROLES)}",
        )
    await ctx.storage.add_vault_member(vault_id, member_user_id, body.vault_role)
    return {"updated": True, "vault_id": vault_id, "user_id": member_user_id, "vault_role": body.vault_role}


@router.delete("/{vault_id}/members/{member_user_id}")
async def remove_vault_member(
    vault_id: str,
    member_user_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Remove a user from a vault. Requires vault admin or platform admin."""
    vault = await resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Vault admin required to manage members.")
    await ctx.storage.remove_vault_member(vault_id, member_user_id)
    return {"removed": True, "vault_id": vault_id, "user_id": member_user_id}


# ── Vault Brain ───────────────────────────────────────────────────────────────

_BRAIN_EDIT_ROLES = ["owner", "admin", "editor"]


class VaultBrainUpdateRequest(BaseModel):
    brain_content: Optional[str] = None


class VaultBrainSettingsRequest(BaseModel):
    brain_edit_role: str = Field(..., description="owner / admin / editor")


def _vault_role_rank(role: Optional[str]) -> int:
    """Lower index = higher privilege. Unknown roles rank last (no access)."""
    try:
        return VAULT_ROLES.index(role)
    except (ValueError, TypeError):
        return len(VAULT_ROLES)


@router.get("/{vault_id}/brain")
async def get_vault_brain(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the vault's brain document. Any vault member can read."""
    await resolve_vault(ctx, user, vault_id)
    return await ctx.storage.get_vault_brain(vault_id)


@router.put("/{vault_id}/brain", status_code=204)
async def update_vault_brain(
    vault_id: str,
    body: VaultBrainUpdateRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update brain_content. Caller must meet or exceed the vault's brain_edit_role."""
    await resolve_vault(ctx, user, vault_id)
    brain = await ctx.storage.get_vault_brain(vault_id)
    edit_role = brain.get("brain_edit_role", "admin")

    user_vault_role = await ctx.storage.get_vault_member_role(vault_id, user.id)
    if user.system_role not in PLATFORM_ADMIN:
        if _vault_role_rank(user_vault_role) > _vault_role_rank(edit_role):
            raise HTTPException(
                status_code=403,
                detail=f"Brain editing requires vault role '{edit_role}' or higher.",
            )
    await ctx.storage.update_vault_brain_content(vault_id, body.brain_content)


@router.patch("/{vault_id}/brain/settings", status_code=204)
async def update_vault_brain_settings(
    vault_id: str,
    body: VaultBrainSettingsRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Update brain_edit_role. Only vault owner or admin may change this."""
    if body.brain_edit_role not in _BRAIN_EDIT_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"brain_edit_role must be one of: {', '.join(_BRAIN_EDIT_ROLES)}",
        )
    await resolve_vault(ctx, user, vault_id)
    user_vault_role = await ctx.storage.get_vault_member_role(vault_id, user.id)
    if user.system_role not in PLATFORM_ADMIN and user_vault_role not in VAULT_ADMIN_AND_ABOVE:
        raise HTTPException(status_code=403, detail="Only vault owner or admin can change brain settings.")
    await ctx.storage.update_vault_brain_edit_role(vault_id, body.brain_edit_role)
