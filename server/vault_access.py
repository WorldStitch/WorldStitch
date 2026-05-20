from __future__ import annotations

from typing import Iterable, List, Optional
from uuid import uuid4

from fastapi import HTTPException, status

from MythosEngine.context.app_context import AppContext
from MythosEngine.models.user import User
from MythosEngine.models.vault import Vault
from server.deps import PLATFORM_ADMIN


def _storage_list_vaults(ctx: AppContext) -> List[Vault]:
    if hasattr(ctx.storage, "list_vaults"):
        try:
            return list(ctx.storage.list_vaults() or [])
        except Exception:
            return []
    return []


def _first_owned_or_member(vaults: Iterable[Vault], user: User) -> Optional[Vault]:
    active = [v for v in vaults if getattr(v, "is_active", True)]
    for vault in active:
        if vault.owner_id == user.id or user.id in (vault.members or []):
            return vault
    return active[0] if active else None


def ensure_personal_vault(ctx: AppContext, user: User) -> Vault:
    existing = _first_owned_or_member(_storage_list_vaults(ctx), user)
    if existing:
        return existing

    preferred_id = "default"
    existing_default = getattr(ctx.storage, "get_vault_by_id", lambda _id: None)(preferred_id)
    vault = Vault(
        id=preferred_id if existing_default is None else str(uuid4()),
        owner_id=user.id,
        name="Default Vault",
        description="Personal campaign vault",
        members=[],
        permissions={},
        settings={},
        is_active=True,
    )
    ctx.storage.save_vault(vault)
    return vault


def is_vault_admin(vault: Vault, user: User, ctx: AppContext) -> bool:
    """True if user is vault owner or belongs to a group with can_admin on this vault."""
    if vault.owner_id == user.id:
        return True
    for group_id in (vault.permissions or {}).keys():
        group = ctx.groups.get_group(group_id)
        if group and user.id in (group.members or []) and (group.permissions or {}).get("can_admin"):
            return True
    return False


def list_accessible_vaults(ctx: AppContext, user: User, all_vaults: bool = False) -> List[Vault]:
    """
    Default: vaults the user owns or is a member of (directly or via groups).
    If all_vaults=True AND user is platform admin, return all active vaults.
    """
    ctx.storage.set_user_context(
        user.id,
        is_admin=user.system_role in PLATFORM_ADMIN,
    )
    vaults = [v for v in _storage_list_vaults(ctx) if getattr(v, "is_active", True)]

    if all_vaults and user.system_role in PLATFORM_ADMIN:
        return vaults

    user_group_ids = set(user.groups or [])
    accessible = []
    for vault in vaults:
        if vault.owner_id == user.id:
            accessible.append(vault)
            continue
        if user.id in (vault.members or []):
            accessible.append(vault)
            continue
        vault_group_ids = set((vault.permissions or {}).keys())
        if user_group_ids & vault_group_ids:
            accessible.append(vault)

    if not accessible:
        return [ensure_personal_vault(ctx, user)]
    return accessible


def resolve_vault(ctx: AppContext, user: User, vault_id: Optional[str]) -> Vault:
    """Resolve a vault the user has access to. Platform admins can access any vault."""
    if not vault_id:
        return list_accessible_vaults(ctx, user)[0]
    if user.system_role in PLATFORM_ADMIN:
        for vault in _storage_list_vaults(ctx):
            if vault.id == vault_id:
                return vault
    accessible = list_accessible_vaults(ctx, user)
    for vault in accessible:
        if vault.id == vault_id:
            return vault
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Vault not found or access denied",
    )
