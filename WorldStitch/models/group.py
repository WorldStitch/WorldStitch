"""
Group model — a party, campaign group, or collaboration team.

Groups tie multiple users together with shared access to vaults and
content. A user can belong to many groups. Groups support named roles
(e.g., GM, player, observer) for future fine-grained permission work.

Multiuser: this is the primary mechanism for shared campaigns.
"""

from typing import Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel

_DEFAULT_PERMISSIONS = {
    "can_read": True,
    "can_write": False,
    "can_delete": False,
    "can_invite": False,
    "can_admin": False,
}


class Group(CoreModel):
    """
    A multiplayer group, party, or campaign team.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel. owner_id is the user who created the group (GM/admin).
    """

    name: str = Field(..., min_length=2, max_length=64, description="Group/campaign/party name.")
    description: Optional[str] = Field(default=None, description="Optional group summary.")
    members: List[str] = Field(default_factory=list, description="User IDs in this group.")
    member_roles: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps user_id -> role string (e.g. 'owner', 'admin', 'member').",
    )
    vault_ids: List[str] = Field(
        default_factory=list,
        description="Vault IDs this group has access to.",
    )
    permissions: Dict[str, bool] = Field(
        default_factory=lambda: {
            "can_read": True,
            "can_write": False,
            "can_delete": False,
            "can_invite": False,
            "can_admin": False,
        },
        description="Fine-grained permission flags for this group.",
    )
    is_active: bool = Field(default=True, description="False to archive/dissolve the group.")
    permissions: Dict[str, bool] = Field(
        default_factory=lambda: dict(_DEFAULT_PERMISSIONS),
        description="Group-level permission flags (can_read, can_write, can_delete, can_invite, can_admin).",
    )
