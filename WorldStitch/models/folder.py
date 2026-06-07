"""
Folder model — organizes notes within a Vault.

Folders form a tree via parent_id. All folders belong to exactly one
Vault. Permissions cascade from the Vault unless overridden here.
"""

from typing import Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Folder(CoreModel):
    """
    A folder for organizing notes within a vault.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    vault_id: str = Field(..., description="Vault this folder belongs to.")
    parent_id: Optional[str] = Field(default=None, description="Parent folder ID for nested structure.")
    name: str = Field(..., min_length=1, max_length=128, description="Folder display name.")
    description: Optional[str] = Field(default=None, description="Optional folder description.")
    group_id: Optional[str] = Field(default=None, description="Group with shared access.")
    permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-user/group permission overrides (read/write/admin).",
    )
    path: Optional[str] = Field(
        default=None,
        description="Relative path within the vault, e.g. 'NPCs/Villains'.",
    )
    note_ids: List[str] = Field(default_factory=list, description="IDs of notes directly in this folder.")
    meta: Dict[str, str] = Field(default_factory=dict, description="Obsidian/YAML or other metadata.")
    record_version: int = Field(default=1, description="Incremented on every save for sync/locking.")
