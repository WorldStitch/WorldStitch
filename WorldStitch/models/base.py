"""
WorldStitch — Core base model.

All data models inherit from CoreModel to guarantee a consistent
set of fields across every entity in the system. This is the single
source of truth for shared metadata — do not duplicate these fields
in subclasses.

Multiuser design notes:
- owner_id: the user who created / owns this record
- Every resource is scoped; nothing exists outside an owner context
- last_modified should be updated on every write via storage layer
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CoreModel(BaseModel):
    """
    Shared base for every WorldStitch data model.

    Fields
    ------
    id : str
        Globally unique UUID4. Generated automatically on creation.
    schema_version : int
        Incremented when the model's field layout changes, enabling
        safe migrations. Never change a record's schema_version manually.
    owner_id : str
        ID of the User who created / owns this record. Required on all
        resources to support multiuser permission checks.
    created_at : datetime
        UTC timestamp set once at creation. Never modified afterward.
    last_modified : datetime
        UTC timestamp updated every time the record is saved. The
        storage layer is responsible for keeping this current.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        populate_by_name=True,
    )

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique UUID4 identifier.",
    )
    schema_version: int = Field(
        default=1,
        description="Model schema version — increment on breaking field changes.",
    )
    owner_id: str = Field(
        ...,
        description="User ID of the record owner. Required for all resources.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of creation. Set once, never changed.",
    )
    last_modified: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of last save. Updated by the storage layer on every write.",
    )
