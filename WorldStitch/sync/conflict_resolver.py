"""
Sync Conflict Resolution Strategy for WorldStitch.

When the same note is edited in two places (e.g. local edits made offline,
then a sync with a remote or shared vault), a conflict arises. This module
defines the strategies for resolving those conflicts and the data types
needed to represent them.

Wire-in:
  - Import ConflictResolver and ConflictStrategy in the sync manager (not yet
    written) when a two-way sync operation detects diverged versions.
  - Use DEFAULT_CONFLICT_STRATEGY as the per-vault default; allow users to
    override it in vault settings.
  - Catch ConflictNeedsReviewError at the sync boundary and surface the
    ConflictRecord to the UI so the user can pick a winner manually.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Default strategy — change here or expose via config UI when settings_manager
# is introduced.
# ---------------------------------------------------------------------------


class ConflictStrategy(Enum):
    """Available strategies for resolving two-way note conflicts."""

    LAST_WRITE_WINS = "last_write_wins"
    OWNER_WINS = "owner_wins"
    MERGE_APPEND = "merge_append"
    FLAG_FOR_REVIEW = "flag_for_review"


DEFAULT_CONFLICT_STRATEGY = ConflictStrategy.LAST_WRITE_WINS


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ConflictRecord:
    """Represents a detected conflict between a local and remote note version."""

    note_path: str
    local_version: str
    remote_version: str
    local_updated_at: datetime
    remote_updated_at: datetime
    resolved: bool = False
    resolution: Optional[str] = None


class ConflictNeedsReviewError(Exception):
    """
    Raised by ConflictResolver when strategy is FLAG_FOR_REVIEW.

    The caller (sync manager or UI layer) must catch this and present the
    conflict to the user before proceeding with any write.

    Attributes
    ----------
    record : ConflictRecord
        The unresolved conflict data, ready to pass to a review dialog.
    """

    def __init__(self, record: ConflictRecord) -> None:
        self.record = record
        super().__init__(
            f"Conflict on '{record.note_path}' requires manual review."
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class ConflictResolver:
    """
    Resolves two-way note conflicts using a configurable strategy.

    Usage
    -----
    resolver = ConflictResolver()
    content = resolver.resolve(record, ConflictStrategy.LAST_WRITE_WINS)
    """

    def resolve(self, record: ConflictRecord, strategy: ConflictStrategy) -> str:
        """
        Apply *strategy* to *record* and return the winning content string.

        Raises
        ------
        ConflictNeedsReviewError
            When *strategy* is FLAG_FOR_REVIEW.
        ValueError
            If an unknown strategy value is passed (guards against future enum
            extensions without matching implementation).
        """
        if strategy == ConflictStrategy.LAST_WRITE_WINS:
            if record.remote_updated_at > record.local_updated_at:
                return record.remote_version
            return record.local_version

        if strategy == ConflictStrategy.OWNER_WINS:
            # Local copy is always the canonical owner copy.
            return record.local_version

        if strategy == ConflictStrategy.MERGE_APPEND:
            return (
                record.local_version
                + "\n\n--- Remote version ---\n\n"
                + record.remote_version
            )

        if strategy == ConflictStrategy.FLAG_FOR_REVIEW:
            raise ConflictNeedsReviewError(record)

        raise ValueError(f"Unknown conflict strategy: {strategy!r}")
