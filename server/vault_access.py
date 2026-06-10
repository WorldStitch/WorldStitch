from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import HTTPException, status

from server.context import AppContext
from server.deps import PLATFORM_ADMIN
from server.storage import Actor
from WorldStitch.models.user import User
from WorldStitch.models.vault import Vault

logger = logging.getLogger(__name__)


async def get_vault_member_role(ctx: AppContext, vault_id: str, user_id: str) -> Optional[str]:
    """Return the user's vault_role in vault_members, or None if not a member."""
    try:
        return await ctx.storage.get_vault_member_role(vault_id, user_id)
    except Exception:
        logger.debug(
            "get_vault_member_role: lookup failed vault=%s user=%s",
            vault_id,
            user_id,
            exc_info=True,
        )
    return None


async def is_vault_admin(vault: Vault, user: User, ctx: AppContext) -> bool:
    """
    Returns True if the user has vault-admin rights for this vault.

    Vault-admin means vault_role is owner or admin in vault_members.
    Platform admins are NOT automatically vault-admins for every vault;
    check that separately when needed.
    """
    role = await get_vault_member_role(ctx, vault.id, user.id)
    if role in ("owner", "admin"):
        return True
    # Legacy fallback: owner_id on the model itself
    return vault.owner_id == user.id


async def list_accessible_vaults(
    ctx: AppContext,
    user: User,
    all_vaults: bool = False,
) -> List[Vault]:
    """
    Default: return vaults the user is a member of via vault_members.
    If all_vaults=True AND user is a platform admin, return ALL active vaults.
    """
    actor = Actor.from_user(user)

    if all_vaults and user.system_role in PLATFORM_ADMIN:
        vaults = await ctx.storage.list_vaults(actor)
        return [v for v in vaults if getattr(v, "is_active", True)]

    # vault_members table is the source of truth
    try:
        vaults = await ctx.storage.list_vaults_for_user(user.id)
        if vaults is not None:
            return vaults
    except Exception:
        logger.warning("list_accessible_vaults: list_vaults_for_user failed", exc_info=True)

    # Fallback: owner_id check only
    all_active = [v for v in await ctx.storage.list_vaults(actor) if getattr(v, "is_active", True)]
    return [v for v in all_active if v.owner_id == user.id]


async def resolve_vault(ctx: AppContext, user: User, vault_id: Optional[str]) -> Vault:
    """
    Resolve a vault by ID for the given user.
    Platform admins can resolve any vault. Regular users must be a member.

    Raises 404 if not found or access denied.
    """
    if not vault_id:
        vaults = await list_accessible_vaults(ctx, user)
        if not vaults:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No accessible vaults found for this user.",
            )
        return vaults[0]

    # Platform admins bypass membership check
    if user.system_role in PLATFORM_ADMIN:
        vault = await ctx.storage.get_vault_by_id(Actor.from_user(user), vault_id)
        if vault:
            return vault

    # vault_members membership check
    try:
        vault = await ctx.storage.get_vault_by_id_for_user(vault_id, user.id)
        if vault:
            return vault
    except Exception:
        logger.debug("resolve_vault: get_vault_by_id_for_user failed", exc_info=True)

    # Fallback: check accessible vaults list
    for vault in await list_accessible_vaults(ctx, user):
        if vault.id == vault_id:
            return vault

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Vault not found or access denied",
    )
