# WorldStitch/ai/core/index_manager.py

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class IndexManager:
    """
    Centralizes all index building, updating, and searching.
    Any AI task can use this class for fast and efficient context retrieval.

    Construction is intentionally cheap — no file I/O, no network calls.
    Call build_index() (in a background thread) to load or create the vector
    index.  All search / mutation methods silently no-op until the index is
    ready so the rest of the app is never blocked.
    """

    def __init__(self, vault_path, api_key, embedding_model="text-embedding-ada-002"):
        self.vault_path = Path(vault_path).resolve()
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.index_dir = str(self.vault_path / "loreai_index")
        self.index = None
        self._retriever = None
        self._engine = None
        # Do NOT call _init_index() here.  The vault may not exist yet and the
        # OpenAI embedding calls would block (and crash) server startup.
        # build_index() is called from a background thread in server/app.py.

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _lazy_imports(self):
        """Import llama_index symbols only when we actually need them.

        Deferring to call-time means an ImportError (missing optional deps) never
        prevents the rest of the server from starting up.
        """
        from llama_index.core import (  # noqa: PLC0415
            SimpleDirectoryReader,
            StorageContext,
            VectorStoreIndex,
            load_index_from_storage,
        )
        from llama_index.core.settings import Settings  # noqa: PLC0415
        from llama_index.embeddings.openai import OpenAIEmbedding  # noqa: PLC0415

        return (
            SimpleDirectoryReader,
            StorageContext,
            VectorStoreIndex,
            load_index_from_storage,
            Settings,
            OpenAIEmbedding,
        )

    def _init_index(self):
        (
            SimpleDirectoryReader,
            StorageContext,
            VectorStoreIndex,
            load_index_from_storage,
            Settings,
            OpenAIEmbedding,
        ) = self._lazy_imports()

        os.environ["OPENAI_API_KEY"] = self.api_key
        Settings.embed_model = OpenAIEmbedding(api_key=self.api_key, model=self.embedding_model)

        if os.path.exists(self.index_dir):
            # Load persistent index from disk
            storage_context = StorageContext.from_defaults(persist_dir=self.index_dir)
            self.index = load_index_from_storage(storage_context)
        else:
            # Build a fresh index from vault documents
            if not self.vault_path.exists():
                logger.warning(
                    "IndexManager: vault path %s does not exist — building empty index",
                    self.vault_path,
                )
                self.index = VectorStoreIndex.from_documents([])
            else:
                docs = SimpleDirectoryReader(str(self.vault_path), recursive=True).load_data()
                for doc in docs:
                    if hasattr(doc, "get_doc_id"):
                        doc.id_ = doc.get_doc_id()
                self.index = VectorStoreIndex.from_documents(docs)
            self.index.storage_context.persist(persist_dir=self.index_dir)

        self._retriever = self.index.as_retriever()

    # ── Public API ────────────────────────────────────────────────────────────

    def build_index(self):
        """Load or build the vector index.  Called from a background thread at startup."""
        self._init_index()

    def search(self, query, top_k=10):
        """Return up to top_k relevant note IDs for a query.

        Returns an empty list if the index has not been built yet.
        """
        if self._retriever is None:
            return []
        docs = self._retriever.retrieve(query)
        return [getattr(doc, "id_", None) for doc in docs][:top_k]

    def rebuild(self):
        """Force a full rebuild of the index from disk."""
        if os.path.exists(self.index_dir):
            import shutil

            shutil.rmtree(self.index_dir)
        self._init_index()

    def update_for_note(self, note_path):
        """
        Incrementally update the index for a specific note.

        Loads the file at note_path, removes any previously-indexed version
        (keyed by its resolved absolute path), then inserts the fresh document.
        Changes are persisted to disk immediately.  No-ops if index not built.
        """
        if self.index is None:
            return

        (SimpleDirectoryReader, *_) = self._lazy_imports()

        note_path = Path(note_path).resolve()
        doc_id = str(note_path)

        docs = SimpleDirectoryReader(input_files=[str(note_path)]).load_data()
        if not docs:
            return

        for doc in docs:
            doc.id_ = doc_id

        try:
            self.index.delete_ref_doc(doc_id, delete_from_docstore=True)
        except Exception:
            pass  # Not yet indexed — safe to ignore

        for doc in docs:
            self.index.insert(doc)
        self.index.storage_context.persist(persist_dir=self.index_dir)
        self._retriever = self.index.as_retriever()

    def delete_note(self, note_id):
        """
        Remove a note from the index by its doc id (resolved absolute path).

        Changes are persisted to disk immediately.  No-ops if index not built.
        """
        if self.index is None:
            return
        try:
            self.index.delete_ref_doc(str(note_id), delete_from_docstore=True)
            self.index.storage_context.persist(persist_dir=self.index_dir)
            self._retriever = self.index.as_retriever()
        except Exception:
            pass  # Note was not in the index — nothing to do

    def get_index(self):
        """Direct access to the underlying index (if needed for advanced ops)."""
        return self.index
