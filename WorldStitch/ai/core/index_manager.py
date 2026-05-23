# WorldStitch/ai/core/index_manager.py

import os
from pathlib import Path

from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.settings import Settings
from llama_index.embeddings.openai import OpenAIEmbedding


class IndexManager:
    """
    Centralizes all index building, updating, and searching.
    Any AI task can use this class for fast and efficient context retrieval.
    """

    def __init__(self, vault_path, api_key, embedding_model="text-embedding-ada-002"):
        self.vault_path = Path(vault_path).resolve()
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.index_dir = str(self.vault_path / "loreai_index")
        self.index = None
        self._retriever = None
        self._engine = None
        self._init_index()

    def _init_index(self):
        os.environ["OPENAI_API_KEY"] = self.api_key
        Settings.embed_model = OpenAIEmbedding(api_key=self.api_key, model=self.embedding_model)
        if os.path.exists(self.index_dir):
            # Load persistent index
            storage_context = StorageContext.from_defaults(persist_dir=self.index_dir)
            self.index = load_index_from_storage(storage_context)
        else:
            # Create and persist index
            docs = SimpleDirectoryReader(str(self.vault_path), recursive=True).load_data()
            for doc in docs:
                if hasattr(doc, "get_doc_id"):
                    doc.id_ = doc.get_doc_id()
            self.index = VectorStoreIndex.from_documents(docs)
            self.index.storage_context.persist(persist_dir=self.index_dir)
        self._retriever = self.index.as_retriever()

    def search(self, query, top_k=10):
        """Return up to top_k relevant note IDs for a query."""
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
        Changes are persisted to disk immediately.
        """
        note_path = Path(note_path).resolve()
        doc_id = str(note_path)

        # Load the updated document
        docs = SimpleDirectoryReader(input_files=[str(note_path)]).load_data()
        if not docs:
            return

        # Assign a stable id so we can replace it cleanly next time
        for doc in docs:
            doc.id_ = doc_id

        # Remove stale version from the index if present
        try:
            self.index.delete_ref_doc(doc_id, delete_from_docstore=True)
        except Exception:
            pass  # Not yet indexed — safe to ignore

        # Insert fresh version and persist
        for doc in docs:
            self.index.insert(doc)
        self.index.storage_context.persist(persist_dir=self.index_dir)

        # Refresh retriever so the update is immediately queryable
        self._retriever = self.index.as_retriever()

    def delete_note(self, note_id):
        """
        Remove a note from the index by its doc id (resolved absolute path).

        Changes are persisted to disk immediately.
        """
        try:
            self.index.delete_ref_doc(str(note_id), delete_from_docstore=True)
            self.index.storage_context.persist(persist_dir=self.index_dir)
            self._retriever = self.index.as_retriever()
        except Exception:
            pass  # Note was not in the index — nothing to do

    def get_index(self):
        """Direct access to the underlying index (if needed for advanced ops)."""
        return self.index
