"""Search query and result types for WorldStitch storage backends."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SearchQuery", "SearchResult"]


@dataclass
class SearchQuery:
    """Parameters for a note search operation."""

    query_str: str
    search_type: str = "keyword"   # "keyword" | "title" | "tag"
    vault_id: str = ""
    top_k: int = 100


@dataclass
class SearchResult:
    """A single note matched by a search query."""

    note_path: str                  # vault-relative path (e.g. "folder/note.md")
    title: str = ""
    snippet: str = ""               # short content preview
    score: float = 1.0
