# WorldStitch/ai/core/model_router.py

import logging
from typing import List, Optional, Tuple

from WorldStitch.ai.ai_logging import estimate_cost, log_api_call
from WorldStitch.ai.core.ai_base import AIInterface
from WorldStitch.ai.core.context_assembler import ContextAssembler
from WorldStitch.ai.core.index_manager import IndexManager
from WorldStitch.ai.core.openai_engine import count_tokens
from WorldStitch.ai.registry import get_plugin
from WorldStitch.config.config import Config

logger = logging.getLogger(__name__)


class ModelRouter(AIInterface):
    """
    Central orchestrator: routes AI tasks to specific backends
    based on configuration and injects vault context into ask().
    """

    TASKS = ["ask", "summarize", "suggest_tags", "propose_links", "search_context"]

    def __init__(self, config: Config, storage=None):
        self._config = config
        self._storage = storage  # shared instance from AppContext — never recreated

        # Set True by the background thread in server/app.py once build_index completes
        self._index_ready: bool = False

        self._backends = {task: self._init_backend(task) for task in self.TASKS}

        # Build IndexManager once at startup, reused across all calls
        self._index_manager = IndexManager(
            vault_path=getattr(self._config, "VAULT_PATH", ""),
            api_key=getattr(self._config, "OPENAI_API_KEY", ""),
            embedding_model=getattr(self._config, "EMBEDDING_MODEL", "text-embedding-ada-002"),
        )

        # Inject shared IndexManager into loreai backend so it doesn't build its own
        loreai_backend = self._backends.get("search_context")
        if loreai_backend and hasattr(loreai_backend, "set_index_manager"):
            loreai_backend.set_index_manager(self._index_manager)

    @property
    def index_manager(self) -> IndexManager:
        """Public accessor for the shared IndexManager."""
        return self._index_manager

    def _init_backend(self, task: str) -> AIInterface:
        key = f"AI_{task.upper()}_BACKEND"
        if hasattr(self._config, key):
            name = getattr(self._config, key)
        elif isinstance(self._config.get("AI_BACKENDS"), dict) and task in self._config.get("AI_BACKENDS"):
            name = self._config.get("AI_BACKENDS")[task]
        else:
            name = getattr(self._config, "AI_BACKEND", None)

        if not name:
            raise ValueError(f"No backend configured for AI task '{task}'")

        plugin_cls = get_plugin(name)
        return plugin_cls(config=self._config)

    def _record_cost(self, operation: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Record token usage against the shared CostTracker, if one is available."""
        ct = getattr(self._storage, "cost_tracker", None)
        if ct is None:
            return
        model = getattr(self._backends.get(operation), "model", "unknown")
        user_id = getattr(self._storage, "_current_user_id", "") or ""
        ct.record(
            user_id=user_id,
            vault_id="",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            operation=operation,
        )

    def _assembler(self, model_name: str) -> ContextAssembler:
        """Return a ContextAssembler using the shared storage and index manager."""
        max_context_tokens = getattr(self._config, "MAX_CONTEXT_TOKENS", 4096)
        return ContextAssembler(
            index_manager=self._index_manager,
            storage=self._storage,
            model=model_name,
            max_context_tokens=max_context_tokens,
        )

    def ask(self, prompt: str) -> Tuple[str, int, int]:
        model_name = getattr(self._backends["ask"], "model", "gpt-3.5-turbo")
        assembler = self._assembler(model_name)
        ctx_result = assembler.assemble_context(prompt, task="ask", top_k=5, min_tokens_for_reply=256)
        full_prompt = ctx_result["context_block"]

        if ctx_result["truncated"]:
            logger.warning(
                "Context truncated in ask: %d notes fit in prompt window.",
                len(ctx_result["included_ids"]),
            )

        prompt_tokens = count_tokens(full_prompt, model_name)
        log_api_call(
            model_name,
            "ask",
            prompt_tokens,
            0,
            estimate_cost(model_name, prompt_tokens, 0),
            success=True,
            error_msg=f"context_note_ids={ctx_result['included_ids']}",
            prompt=full_prompt,
        )

        result = self._backends["ask"].ask(full_prompt)
        _, p_tok, c_tok = result
        self._record_cost("ask", p_tok, c_tok)
        return result

    def summarize(self, text: str) -> Tuple[str, int, int]:
        model_name = getattr(self._backends["summarize"], "model", "gpt-3.5-turbo")
        assembler = self._assembler(model_name)
        ctx_result = assembler.assemble_context(
            query="",
            task="summarize",
            top_k=0,
            extra_ids=[],
            user_prompt=f"Summarize the following note:\n\n{text}",
            min_tokens_for_reply=256,
        )
        result = self._backends["summarize"].summarize(ctx_result["context_block"])
        _, p_tok, c_tok = result
        self._record_cost("summarize", p_tok, c_tok)
        return result

    def suggest_tags(self, text: str) -> Tuple[str, int, int]:
        model_name = getattr(self._backends["suggest_tags"], "model", "gpt-3.5-turbo")
        assembler = self._assembler(model_name)
        ctx_result = assembler.assemble_context(
            query="",
            task="suggest_tags",
            top_k=0,
            extra_ids=[],
            user_prompt=f"Suggest tags for this note:\n\n{text}",
            min_tokens_for_reply=128,
        )
        result = self._backends["suggest_tags"].suggest_tags(ctx_result["context_block"])
        _, p_tok, c_tok = result
        self._record_cost("suggest_tags", p_tok, c_tok)
        return result

    def propose_links(self, text: str, note_names: List[str]) -> Tuple[str, int, int]:
        model_name = getattr(self._backends["propose_links"], "model", "gpt-3.5-turbo")
        assembler = self._assembler(model_name)
        ctx_result = assembler.assemble_context(
            query="",
            task="propose_links",
            top_k=0,
            extra_ids=[],
            user_prompt=(
                f"Suggest internal links for the following note, considering these "
                f"possible note names:\n{', '.join(note_names)}\n\nNote:\n{text}"
            ),
            min_tokens_for_reply=256,
        )
        result = self._backends["propose_links"].propose_links(ctx_result["context_block"], note_names)
        _, p_tok, c_tok = result
        self._record_cost("propose_links", p_tok, c_tok)
        return result

    def search_context(self, query: str, top_k: int = 10) -> List[str]:
        return self._backends["search_context"].search_context(query, top_k)

    def get_backend(self, task: str) -> Optional[AIInterface]:
        return self._backends.get(task)

    def update_api_key(self, new_key: str):
        self._config.OPENAI_API_KEY = new_key
        for backend in self._backends.values():
            if hasattr(backend, "update_api_key"):
                backend.update_api_key(new_key)

    def update_models(self, embedding_model: str, completion_model: str):
        self._config.EMBEDDING_MODEL = embedding_model
        self._config.COMPLETION_MODEL = completion_model
        for backend in self._backends.values():
            if hasattr(backend, "update_models"):
                backend.update_models(embedding_model, completion_model)

    def update_max_tokens(self, max_tokens: int):
        self._config.MAX_TOKENS = max_tokens
        for backend in self._backends.values():
            if hasattr(backend, "update_max_tokens"):
                backend.update_max_tokens(max_tokens)


def get_model_backend(config: Config, storage=None) -> AIInterface:
    return ModelRouter(config, storage=storage)
