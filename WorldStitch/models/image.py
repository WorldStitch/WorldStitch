"""
Image model — any image asset in the system (AI-generated art, portraits, handouts).

Unlike maps, images are not necessarily geographic. They cover character
portraits, scene illustrations, item art, and any other visual asset.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Image(CoreModel):
    """
    An image asset (AI-generated or uploaded).

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    vault_id: str = Field(..., description="Vault/campaign this image belongs to.")
    file_path: str = Field(..., description="File path or URL to the image asset.")
    name: Optional[str] = Field(default=None, description="Title or caption.")
    description: Optional[str] = Field(default=None, description="Context, e.g. 'AI: Village at night'.")
    prompt: Optional[str] = Field(default=None, description="AI prompt used to generate this image, if any.")
    source: Optional[str] = Field(default=None, description="Generation source (model name) or 'uploaded'.")
    linked_notes: List[str] = Field(default_factory=list, description="Note IDs this image is attached to.")
    tags: List[str] = Field(default_factory=list, description="Tags for search and scene type.")
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra metadata: style, AI parameters, rating, etc.",
    )
    is_public: bool = Field(default=True, description="Visible to all players in the vault.")
    is_deleted: bool = Field(default=False, description="Soft delete flag.")
    record_version: int = Field(default=1, description="Incremented on every save for sync/locking.")
