# WorldStitch/ai/ai_base.py

from abc import ABC, abstractmethod
from typing import List, Tuple


class AIInterface(ABC):
    """
    Abstract base class for all AI backends.
    Every implementation must provide these methods following the contract:
      - ask: free-form prompting
      - summarize: text summarization
      - suggest_tags: tag generation
      - propose_links: internal link suggestions
      - search_context: retrieval over indexed notes
    """

    @abstractmethod
    def ask(self, prompt: str) -> Tuple[str, int, int]:
        """
        Send a free-form prompt to the AI and return a tuple of:
        (response_text, prompt_tokens, response_tokens).
        """
        pass

    @abstractmethod
    def summarize(self, text: str) -> Tuple[str, int, int]:
        pass

    @abstractmethod
    def suggest_tags(self, text: str) -> Tuple[str, int, int]:
        """
        Given note text, return suggested tags as a comma-separated string,
        plus token counts.
        """
        pass

    @abstractmethod
    def propose_links(self, text: str, note_names: List[str]) -> Tuple[str, int, int]:
        """
        Suggest internal links from `note_names` based on `text`.
        Returns (links_csv, prompt_tokens, response_tokens).
        """
        pass

    @abstractmethod
    def search_context(self, query: str, top_k: int = 10) -> List[str]:
        """
        Return up to `top_k` relevant note paths for the given query by
        performing retrieval over an indexed store.
        """
        pass
