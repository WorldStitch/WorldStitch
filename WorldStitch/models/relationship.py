"""
Relationship model — first-class edge object for WorldStitch.

A Relationship connects any two entities (notes, characters, locations,
items, factions, etc.) via a typed, directed or bidirectional edge.
The type registry lives in relationship_types.py; custom types are also
supported via free-text relationship_type values.
"""

from typing import Dict, Literal, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Relationship(CoreModel):
    """
    A typed edge between two entities within a vault.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel.
    """

    source_id: str = Field(..., description="ID of the source entity.")
    target_id: str = Field(..., description="ID of the target entity.")
    relationship_type: str = Field(
        ...,
        description="Canonical type string (from RELATIONSHIP_TYPES) or custom label.",
    )
    direction: Literal["unidirectional", "bidirectional"] = Field(
        default="bidirectional",
        description="Whether the edge is directed (source→target only) or mutual.",
    )
    label: Optional[str] = Field(
        default=None,
        description="Custom display override. Falls back to relationship_type when None.",
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="AI context relevance weight (0.0–1.0).",
    )
    vault_id: str = Field(..., description="Vault this relationship belongs to.")
    meta: Dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value metadata for extensions.",
    )
