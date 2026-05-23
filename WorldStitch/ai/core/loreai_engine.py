# WorldStitch/ai/core/loreai_engine.py

from typing import List, Tuple

from WorldStitch.ai.core.ai_base import AIInterface
from WorldStitch.ai.registry import register_plugin
from WorldStitch.config.config import Config


@register_plugin("loreai")
class LoreaiAI(AIInterface):
    """
    LoreAI backend: provides search_context via the shared IndexManager.
    The IndexManager is owned by ModelRouter and injected here after construction
    via set_index_manager(). This avoids building the vector index twice.

    All other AI tasks (ask, summarize, suggest_tags, propose_links) are
    handled by separate backends routed through ModelRouter.
    """

    def __init__(self, config: Config = None):
        self.config = config
        self._index_manager = None  # injected by ModelRouter after init

    def set_index_manager(self, index_manager):
        """Called by ModelRouter to inject the shared IndexManager instance."""
        self._index_manager = index_manager

    def update_api_key(self, new_key: str):
        if self.config:
            self.config.OPENAI_API_KEY = new_key
        if self._index_manager:
            self._index_manager.api_key = new_key

    def update_max_tokens(self, max_tokens: int):
        pass  # not applicable to retrieval

    def update_models(self, embedding_model: str, completion_model: str):
        pass  # embedding model changes require an index rebuild; handled separately

    def ask(self, prompt: str) -> Tuple[str, int, int]:
        raise RuntimeError("LoreaiAI is a retrieval-only engine. Route 'ask' through ModelRouter to an LLM backend.")

    def summarize(self, text: str) -> Tuple[str, int, int]:
        raise RuntimeError("LoreaiAI is a retrieval-only engine. Route 'summarize' through ModelRouter to an LLM backend.")

    def suggest_tags(self, text: str) -> Tuple[str, int, int]:
        raise RuntimeError("LoreaiAI is a retrieval-only engine. Route 'suggest_tags' through ModelRouter to an LLM backend.")

    def propose_links(self, text: str, note_names: List[str]) -> Tuple[str, int, int]:
        raise RuntimeError("LoreaiAI is a retrieval-only engine. Route 'propose_links' through ModelRouter to an LLM backend.")

    def search_context(self, query: str, top_k: int = 10) -> List[str]:
        """Retrieve up to top_k relevant note IDs for the given query."""
        if self._index_manager is None:
            raise RuntimeError("LoreaiAI has no IndexManager. Call set_index_manager() before using search_context.")
        return self._index_manager.search(query, top_k=top_k)
