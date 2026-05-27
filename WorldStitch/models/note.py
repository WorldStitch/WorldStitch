"""
Note model — the primary content unit in WorldStitch.

Notes hold lore, session logs, NPC descriptions, item cards, location
entries, and anything else a DM or player wants to record. They live
inside a Vault, optionally inside a Folder, and are always owned by a User.

Multiuser: every note carries owner_id (from CoreModel), a group_id for
shared access, and a permissions dict for per-user/group overrides.
"""

from typing import Dict, List, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Note(CoreModel):
    """
    A persistent note for lore, session logs, items, NPCs, locations, etc.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    vault_id: str = Field(..., description="Vault/campaign this note belongs to.")
    folder_id: Optional[str] = Field(default=None, description="Parent folder ID, if any.")
    title: str = Field(..., min_length=1, max_length=128, description="Note title or heading.")
    content: str = Field(default="", description="Markdown/rich text content.")
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for organization and search (user or AI-generated).",
    )
    group_id: Optional[str] = Field(
        default=None,
        description="Group ID with shared edit/view access, if any.",
    )
    permissions: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-user or per-group permission overrides. Keys are IDs, values are roles (read/write).",
    )
    links: List[str] = Field(
        default_factory=list,
        description="IDs of notes this note links to (wiki-style internal links).",
    )
    attachments: List[str] = Field(
        default_factory=list,
        description="Attached asset IDs (images, sounds, maps, etc.).",
    )
    ai_summary: Optional[str] = Field(
        default=None,
        description="AI-generated summary or search snippet.",
    )
    meta: Dict[str, str] = Field(
        default_factory=dict,
        description="YAML frontmatter or Obsidian-compatible metadata.",
    )
    is_deleted: bool = Field(default=False, description="Soft delete flag — excluded from queries but not removed.")
