from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User
from MythosEngine.models.vault import Vault
from server.deps import PLATFORM_ADMIN, get_ctx, get_current_user
from server.vault_access import list_accessible_vaults, resolve_vault

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
    record_version: int = 1
    created_at: Optional[datetime] = None


class CreateVaultRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    description: Optional[str] = None


class UpdateVaultRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=64)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    shared_group_id: Optional[str] = None
    backup_cron: Optional[str] = None


def _to_response(vault: Vault) -> VaultResponse:
    return VaultResponse(**vault.model_dump())


@router.get("/", response_model=List[VaultResponse])
async def list_vaults(
    all: bool = Query(False, description="Platform admins only: return all vaults (explore/analytics mode)"),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    return [_to_response(vault) for vault in list_accessible_vaults(ctx, user, all_vaults=all)]


@router.get("/{vault_id}", response_model=VaultResponse)
async def get_vault(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    return _to_response(vault)


@router.post("/", response_model=VaultResponse, status_code=status.HTTP_201_CREATED)
async def create_vault(
    body: CreateVaultRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = ctx.vaults.create_vault(
        name=body.name,
        owner_id=user.id,
        description=body.description,
    )
    return _to_response(vault)


@router.put("/{vault_id}", response_model=VaultResponse)
async def update_vault(
    vault_id: str,
    body: UpdateVaultRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner or an admin can update this vault")
    if body.name is not None:
        vault.name = body.name
    if body.description is not None:
        vault.description = body.description
    if body.is_active is not None:
        vault.is_active = body.is_active
    if body.shared_group_id:
        group = ctx.groups.get_group(body.shared_group_id)
        if not group or not getattr(group, "is_active", True):
            raise HTTPException(status_code=404, detail="Group not found")
        vault.permissions = dict(getattr(vault, "permissions", {}) or {})
        vault.permissions[body.shared_group_id] = "write"
        if vault.id not in (group.vault_ids or []):
            group.vault_ids.append(vault.id)
            ctx.groups.update_group(group)
    if body.backup_cron:
        if hasattr(ctx.storage, "schedule_vault_backup"):
            ctx.storage.schedule_vault_backup(vault.id, body.backup_cron)
        vault.settings["backup_cron"] = body.backup_cron
    ctx.vaults.update_vault(vault)
    return _to_response(vault)


@router.delete("/{vault_id}")
async def delete_vault(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    vault = resolve_vault(ctx, user, vault_id)
    if vault.owner_id != user.id and user.system_role not in PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail="Only the owner or an admin can delete this vault")
    ctx.vaults.delete_vault(vault_id, actor_id=user.id)
    return {"deleted": True, "id": vault_id}


@router.get("/{vault_id}/export")
async def export_vault(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    resolve_vault(ctx, user, vault_id)
    if not hasattr(ctx.storage, "export_vault_zip"):
        raise HTTPException(status_code=501, detail="Vault export is not supported by this backend")
    content = ctx.storage.export_vault_zip(vault_id)
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
    if not hasattr(ctx.storage, "import_vault_zip"):
        raise HTTPException(status_code=501, detail="Vault import is not supported by this backend")
    payload = await file.read()
    vault = ctx.storage.import_vault_zip(payload, owner_id=user.id, name=name)
    return _to_response(vault)


@router.put("/{vault_id}/backup")
async def configure_backup(
    vault_id: str,
    cron: str = Query(..., min_length=5),
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    resolve_vault(ctx, user, vault_id)
    if not hasattr(ctx.storage, "schedule_vault_backup"):
        raise HTTPException(status_code=501, detail="Backup scheduling is not supported by this backend")
    return ctx.storage.schedule_vault_backup(vault_id, cron)
