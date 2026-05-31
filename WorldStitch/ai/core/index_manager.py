# WorldStitch/ai/core/index_manager.py

import os
from pathlib import Path


class IndexManager:
    """
    Centralizes all index building, updating, and searching.

    Lazy by design: the index is NOT built in __init__. Call build_index()
    (typically from a background thread) before calling search(). Until then,
    search() returns an empty list so the rest of the app can still start.
    """

    def __init__(self, vault_path, api_key, embedding_model="text-embedding-ada-002"):
        self.vault_path = Path(vault_path).resolve()
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.index_dir = str(self.vault_path / "loreai_index")
        self.index = None
        self._retriever = None

    def build_index(self):
        """
        Build (or load from disk) the vector index.

        Called from the background thread in server/app.py so startup is
        non-blocking. Safe to call multiple times — subsequent calls reload
        the on-disk index without re-embedding.
        """
        try:
            from llama_index.core import (
                SimpleDirectoryReader,
                StorageContext,
                VectorStoreIndex,
                load_index_from_storage,
            )
            from llama_index.core.settings import Settings
            from llama_index.embeddings.openai import OpenAIEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "llama-index packages are required for vector indexing. "
                "Install them with: pip install llama-index llama-index-embeddings-openai"
            ) from exc

        os.environ["OPENAI_API_KEY"] = self.api_key
        Settings.embed_model = OpenAIEmbedding(api_key=self.api_key, model=self.embedding_model)

        if os.path.exists(self.index_dir):
            storage_context = StorageContext.from_defaults(persist_dir=self.index_dir)
            self.index = load_index_from_storage(storage_context)
        else:
            # Load documents if the vault path exists and contains files.
            # If the vault is empty or DB-backed (no local files), build an
            # empty index so the banner clears immediately rather than failing.
            docs = []
            if self.vault_path.exists():
                try:
                    docs = SimpleDirectoryReader(str(self.vault_path), recursive=True).load_data()
                except Exception:
                    docs = []
            for doc in docs:
                if hasattr(doc, "get_doc_id"):
                    doc.id_ = doc.get_doc_id()
            self.index = VectorStoreIndex.from_documents(docs)
            self.index.storage_context.persist(persist_dir=self.index_dir)

        self._retriever = self.index.as_retriever()

    def search(self, query, top_k=10):
        """Return up to top_k relevant note IDs for a query. Returns [] if index not built yet."""
        if self._retriever is None:
            return []
        docs = self._retriever.retrieve(query)
        return [getattr(doc, "id_", None) for doc in docs][:top_k]

    def rebuild(self):
        """Force a full rebuild of the index from disk."""
        if os.path.exists(self.index_dir):
            import shutil

            shutil.rmtree(self.index_dir)
        self.index = None
        self._retriever = None
        self.build_index()

    def update_for_note(self, note_path):
        """
        Incrementally update the index for a specific note.
        No-op if the index has not been built yet.
        """
        if self.index is None:
            return

        from llama_index.core import SimpleDirectoryReader

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
            pass

        for doc in docs:
            self.index.insert(doc)
        self.index.storage_context.persist(persist_dir=self.index_dir)

        self._retriever = self.index.as_retriever()

    def delete_note(self, note_id):
        """Remove a note from the index by its doc id. No-op if index not built yet."""
        if self.index is None:
            return
        try:
            self.index.delete_ref_doc(str(note_id), delete_from_docstore=True)
            self.index.storage_context.persist(persist_dir=self.index_dir)
            self._retriever = self.index.as_retriever()
        except Exception:
            pass

    def get_index(self):
        """Direct access to the underlying index (if needed for advanced ops)."""
        return self.index
