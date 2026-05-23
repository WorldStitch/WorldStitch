"""
Sound model — audio assets for ambient music, effects, and atmosphere.

Sounds can be linked to notes or scenes and played during sessions.
GMs control visibility so surprise ambushes don't get spoiled.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Sound(CoreModel):
    """
    An audio asset for ambient sound, music, or effects.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    vault_id: str = Field(..., description="Vault/campaign this sound belongs to.")
    group_id: Optional[str] = Field(default=None, description="Group/party with access.")
    name: str = Field(..., min_length=1, max_length=128, description="Sound title or filename.")
    description: Optional[str] = Field(default=None, description="Description or usage notes.")
    file_path: str = Field(..., description="Path or URL to the audio file.")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization and search.")
    linked_notes: List[str] = Field(default_factory=list, description="Note IDs this sound is attached to.")
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra metadata: duration, format, BPM, etc.",
    )
    is_public: bool = Field(default=True, description="Visible to all players in the vault.")
    is_deleted: bool = Field(default=False, description="Soft delete flag.")
    record_version: int = Field(default=1, description="Incremented on every save for sync/locking.")
