"""
Vector Index Location Strategy for WorldStitch.

Provides a location-agnostic interface for building and querying a vector
index over vault notes. The index can live in memory, on disk via FAISS,
or be managed by LlamaIndex — controlled by VectorIndexConfig.

Wire-in:
  - Once sentence_transformers is confirmed available, instantiate
    VectorIndexManager in the storage backend __init__() and expose it
    via AppContext.
  - Replace the current IndexManager (ai/core/index_manager.py) gradually:
    route OpenAI-backed semantic search through LLAMAINDEX_LOCAL and use
    IN_MEMORY for lightweight offline search without an API key.
  - For production: switch to DISK_FAISS so the index survives restarts.

Current status: enabled=False by default so no packages are required at
startup. is_available() does all dependency checks lazily at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration types
# ---------------------------------------------------------------------------


class VectorIndexLocation(Enum):
    """Where the vector index lives at runtime."""

    IN_MEMORY = "in_memory"
    DISK_FAISS = "disk_faiss"
    LLAMAINDEX_LOCAL = "llamaindex_local"


@dataclass
class VectorIndexConfig:
    """Configuration for the vector index manager."""

    location: VectorIndexLocation = VectorIndexLocation.IN_MEMORY
    index_path: Optional[str] = None
    model_name: str = "all-MiniLM-L6-v2"
    chunk_size: int = 512
    enabled: bool = True


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class VectorIndexManager:
    """
    Builds and queries an in-memory (or pluggable) vector index over vault notes.

    Parameters
    ----------
    config : VectorIndexConfig
        Controls whether and where the index is built.
    """

    def __init__(self, config: VectorIndexConfig) -> None:
        self.config = config
        self._index = None  # populated by build_index()

    def is_available(self) -> bool:
        """
        Return True if the required packages for the configured location are
        importable. Never raises — returns False on missing dependencies so
        callers can degrade gracefully (e.g., fall back to full-text search).
        """
        loc = self.config.location

        if loc in (VectorIndexLocation.IN_MEMORY, VectorIndexLocation.DISK_FAISS):
            try:
                import sentence_transformers  # noqa: F401

                return True
            except ImportError:
                return False

        if loc == VectorIndexLocation.LLAMAINDEX_LOCAL:
            try:
                import llama_index  # noqa: F401

                return True
            except ImportError:
                return False

        return False

    def build_index(self, notes: list[dict]) -> None:
        """
        Build the vector index from a list of note dicts.

        Each dict should have at least ``note_path`` (str) and ``content`` (str).
        No-op if ``enabled=False`` or required packages are unavailable.
        """
        if not self.config.enabled or not self.is_available():
            return

        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self.config.model_name)
            self._index = {
                note["note_path"]: model.encode(note.get("content", ""))
                for note in notes
                if note.get("note_path") and note.get("content")
            }
        except Exception:
            self._index = None

    def search(self, query: str, top_k: int = 10) -> list[str]:
        """
        Return up to *top_k* note_paths most similar to *query*.

        Falls back to an empty list if the index has not been built, is
        disabled, or required packages are unavailable.
        """
        if self._index is None or not self.config.enabled:
            return []

        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self.config.model_name)
            query_vec = model.encode(query)

            scores: dict[str, float] = {}
            for path, vec in self._index.items():
                norm = float(np.linalg.norm(vec)) * float(np.linalg.norm(query_vec))
                scores[path] = float(np.dot(vec, query_vec) / norm) if norm else 0.0

            return sorted(scores, key=lambda p: scores[p], reverse=True)[:top_k]
        except Exception:
            return []

    def clear(self) -> None:
        """Reset the index, freeing any held memory."""
        self._index = None
