"""
Character model — PCs, NPCs, monsters, and any named entity in the world.

Characters belong to a Vault and are always owned by a User (even NPCs
are owned by the GM's user account). The is_npc flag distinguishes
player characters from GM-controlled entities.

Multiuser: group_id and permissions support party-level visibility,
e.g., a GM can mark an NPC's secrets as GM-only.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Character(CoreModel):
    """
    A character (PC, NPC, monster, etc.) in a campaign.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    vault_id: str = Field(..., description="Vault/campaign this character belongs to.")
    campaign_id: Optional[str] = Field(default=None, description="Campaign ID (preferred over vault_id).")
    name: str = Field(..., min_length=1, max_length=128, description="Character name.")
    description: Optional[str] = Field(default=None, description="Bio, summary, or background.")
    group_id: Optional[str] = Field(default=None, description="Group/party with access to this character.")
    permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-user/group permission overrides (read/write/admin).",
    )
    is_npc: bool = Field(
        default=False,
        description="True if GM-controlled NPC; False if player character.",
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Flexible key-value stats: HP, AC, skills, attributes, etc.",
    )
    tags: List[str] = Field(default_factory=list, description="Tags for search, AI context, and grouping.")
    note_ids: List[str] = Field(default_factory=list, description="IDs of notes attached to this character.")
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom fields, YAML frontmatter, or system-specific data.",
    )
    ai_memory: Optional[str] = Field(
        default=None,
        description="AI-generated or user-written memory/log for this character.",
    )
    is_deleted: bool = Field(default=False, description="Soft delete flag.")
