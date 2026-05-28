"""
Vault model — the top-level container for a campaign or world.

A Vault holds all notes, characters, maps, folders, and assets for one
campaign. Users can own multiple vaults (e.g., one per campaign). The
owner is always a single user; additional members are granted access
via the members list and permissions dict.

Multiuser: members list + permissions dict support DM-owned vaults with
player access, shared worldbuilding vaults, and solo play.
"""

from typing import Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Vault(CoreModel):
    """
    A campaign or world container — the root of all content.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    name: str = Field(..., min_length=2, max_length=64, description="Vault/campaign name.")
    description: Optional[str] = Field(default=None, description="Campaign or world summary.")
    members: List[str] = Field(
        default_factory=list,
        description="User IDs with access to this vault (beyond the owner).",
    )
    permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-user/group permission overrides (read/write).",
    )
    is_active: bool = Field(default=True, description="False to archive/disable this vault.")
    settings: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-vault config: AI model overrides, export settings, UI prefs, etc.",
    )
    vault_type: str = Field(
        default="worldbuilding",
        description="Media type — controls UI terminology (worldbuilding, tabletop, video_game, novel, film, custom).",
    )
    record_version: int = Field(
        default=1,
        description="Incremented on every save — used for optimistic locking and sync.",
    )
