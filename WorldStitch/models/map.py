"""
Map model — a map asset (image, grid, handout) for a campaign.

Maps live inside a Vault and can be linked to notes for lore context.
They support fine-grained permissions so GMs can hide maps from players
until the right moment.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Map(CoreModel):
    """
    A map asset for a campaign.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    vault_id: str = Field(..., description="Vault/campaign this map belongs to.")
    group_id: Optional[str] = Field(default=None, description="Group/party with access.")
    name: str = Field(..., min_length=1, max_length=128, description="Map title.")
    description: Optional[str] = Field(default=None, description="Map summary or context.")
    map_type: str = Field(default="region", description="Map category: region, dungeon, city, or world.")
    file_path: str = Field(default="", description="Relative or absolute path to the map image asset.")
    markers: List[Dict[str, Any]] = Field(default_factory=list, description="Map markers: [{id, x, y, label, note_id}].")
    permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-user/group permission overrides (read/write/admin).",
    )
    tags: List[str] = Field(default_factory=list, description="Tags for search and grouping.")
    linked_notes: List[str] = Field(
        default_factory=list,
        description="Note IDs linked to this map for lore and AI context.",
    )
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra metadata: grid size, scale, region, custom fields, etc.",
    )
    is_deleted: bool = Field(default=False, description="Soft delete flag.")
    record_version: int = Field(default=1, description="Incremented on every save for sync/locking.")
