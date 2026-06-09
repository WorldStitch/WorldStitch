from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import HTTPException, status

from server.deps import PLATFORM_ADMIN
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User
from WorldStitch.models.vault import Vault

logger = logging.getLogger(__name__)


def _storage_list_vaults(ctx: AppContext) -> List[Vault]:
    if hasattr(ctx.storage, "list_vaults"):
        try:
            return list(ctx.storage.list_vaults() or [])
        except Exception:
            logger.warning("_storage_list_vaults: failed to enumerate vaults", exc_info=True)
            return []
    return []


def get_vault_member_role(ctx: AppContext, vault_id: str, user_id: str) -> Optional[str]:
    """Return the user's vault_role in vault_members, or None if not a member."""
    if hasattr(ctx.storage, "get_vault_member_role"):
        try:
            return ctx.storage.get_vault_member_role(vault_id, user_id)
        except Exception:
            logger.debug(
                "get_vault_member_role: lookup failed vault=%s user=%s",
                vault_id,
                user_id,
                exc_info=True,
            )
    return None


def is_vault_admin(vault: Vault, user: User, ctx: AppContext) -> bool:
    """
    Returns True if the user has vault-admin rights for this vault.

    Vault-admin means vault_role is owner or admin in vault_members.
    Platform admins are NOT automatically vault-admins for every vault;
    check that separately when needed.
    """
    role = get_vault_member_role(ctx, vault.id, user.id)
    if role in ("owner", "admin"):
        return True
    # Legacy fallback: owner_id on the model itself
    return vault.owner_id == user.id


def list_accessible_vaults(
    ctx: AppContext,
    user: User,
    all_vaults: bool = False,
) -> List[Vault]:
    """
    Default: return vaults the user is a member of via vault_members.
    If all_vaults=True AND user is a platform admin, return ALL active vaults.
    """
    ctx.storage.set_user_context(
        user.id,
        is_admin=user.system_role in PLATFORM_ADMIN,
    )

    all_active = [v for v in _storage_list_vaults(ctx) if getattr(v, "is_active", True)]

    if all_vaults and user.system_role in PLATFORM_ADMIN:
        return all_active

    # Use vault_members table if available (preferred)
    if hasattr(ctx.storage, "list_vaults_for_user"):
        try:
            vaults = ctx.storage.list_vaults_for_user(user.id)
            if vaults is not None:
                return vaults
        except Exception:
            logger.warning("list_accessible_vaults: list_vaults_for_user failed", exc_info=True)

    # Fallback: owner_id check only
    return [v for v in all_active if v.owner_id == user.id]


def resolve_vault(ctx: AppContext, user: User, vault_id: Optional[str]) -> Vault:
    """
    Resolve a vault by ID for the given user.
    Platform admins can resolve any vault. Regular users must be a member.

    Raises 404 if not found or access denied.
    """
    if not vault_id:
        vaults = list_accessible_vaults(ctx, user)
        if not vaults:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No accessible vaults found for this user.",
            )
        return vaults[0]

    # Platform admins bypass membership check
    if user.system_role in PLATFORM_ADMIN:
        for vault in _storage_list_vaults(ctx):
            if vault.id == vault_id:
                return vault

    # Use vault_members table if the storage backend supports it
    if hasattr(ctx.storage, "get_vault_by_id_for_user"):
        try:
            vault = ctx.storage.get_vault_by_id_for_user(vault_id, user.id)
            if vault:
                return vault
        except Exception:
            logger.debug("resolve_vault: get_vault_by_id_for_user failed", exc_info=True)

    # Fallback: check accessible vaults list
    for vault in list_accessible_vaults(ctx, user):
        if vault.id == vault_id:
            return vault

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Vault not found or access denied",
    )
