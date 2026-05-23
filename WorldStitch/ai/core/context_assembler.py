from typing import Any, Dict, List, Optional, Tuple

from WorldStitch.ai.ai_logging import count_tokens
from WorldStitch.ai.core.index_manager import IndexManager
from WorldStitch.models.relationship_types import get_inverse_label


class ContextAssembler:
    """
    Assembles optimized context blocks for any AI task, with in-memory caching.
    - Handles token budgeting, note ordering, and truncation.
    - Modular: Each AI task can define its own context policy.
    - Caches context assembly and token counts for efficiency.
    """

    # Static (process-wide) caches; you could make these instance-based if needed
    _context_cache: Dict[Tuple, Dict[str, Any]] = {}
    _token_cache: Dict[Tuple[str, str], int] = {}

    def __init__(
        self,
        index_manager: IndexManager,
        storage,
        model: str = "gpt-3.5-turbo",
        max_context_tokens: int = 2048,
    ):
        self.index_manager = index_manager
        self.storage = storage
        self.model = model
        self.max_context_tokens = max_context_tokens

    def _count_tokens_cached(self, text: str) -> int:
        key = (self.model, text[:128])  # Caches by model + note snippet
        if key in self._token_cache:
            return self._token_cache[key]
        tokens = count_tokens(text, self.model)
        self._token_cache[key] = tokens
        return tokens

    def assemble_context(
        self,
        query: str,
        task: str = "ask",
        top_k: int = 5,
        extra_ids: Optional[List[str]] = None,
        prompt_preamble: Optional[str] = None,
        user_prompt: Optional[str] = None,
        min_tokens_for_reply: int = 256,
    ) -> Dict[str, Any]:
        """
        Main entry point: build a context window for a given AI task, with in-memory cache.
        Returns:
            {
                "context_block": str,
                "included_ids": [list of note IDs],
                "prompt_token_count": int,
                "truncated": bool,
            }
        """
        cache_key = (
            self.model,
            query,
            task,
            top_k,
            tuple(extra_ids) if extra_ids else (),
            prompt_preamble,
            user_prompt,
            min_tokens_for_reply,
        )
        # Check context assembly cache first
        if cache_key in self._context_cache:
            return self._context_cache[cache_key]

        # 1. Get relevant note IDs (safeguard: skip search if query is empty/None)
        if not query or not query.strip():
            ids = []
        else:
            ids = self.index_manager.search(query, top_k)
        if extra_ids:
            ids = list(dict.fromkeys(ids + extra_ids))  # Remove dups, keep order
            # 2. Load note texts
        note_texts = []
        id_list = []
        for note_id in ids:
            try:
                text = self.storage.read_note(note_id)
                note_texts.append((note_id, text))
                id_list.append(note_id)
            except Exception:
                continue

        # 3. Build context, respecting token budget
        preamble = prompt_preamble or "Relevant notes:\n\n"
        prompt_base = user_prompt or f"User query:\n{query}"
        context_lines = []
        token_budget = (
            self.max_context_tokens
            - self._count_tokens_cached(preamble)
            - self._count_tokens_cached(prompt_base)
            - min_tokens_for_reply
        )

        prompt_token_count = 0
        included_ids = []
        truncated = False

        for note_id, note_text in note_texts:
            tokens = self._count_tokens_cached(note_text)
            if prompt_token_count + tokens > token_budget:
                truncated = True
                break
            context_lines.append(note_text)
            included_ids.append(note_id)
            prompt_token_count += tokens

        # Append typed relationship context for included entities
        rel_block = self._build_relationship_context(included_ids)
        notes_section = "\n\n".join(context_lines)
        if rel_block:
            notes_section = notes_section + "\n\n" + rel_block if notes_section else rel_block

        context_block = preamble + notes_section + "\n\n" + prompt_base
        total_tokens = self._count_tokens_cached(context_block)

        result = {
            "context_block": context_block,
            "included_ids": included_ids,
            "prompt_token_count": total_tokens,
            "truncated": truncated,
        }

        # Save to cache
        self._context_cache[cache_key] = result
        return result

    def _build_relationship_context(self, entity_ids: List[str], vault_id: str = "") -> str:
        """Query typed relationships for entity_ids and return a formatted block.

        Replaces the flat "Linked notes: [id1, id2]" pattern with typed statements:
        "Relationships: Mira is an ally of Dax (bidirectional), Mira killed Lord Vane
        (unidirectional → Lord Vane was killed by Mira)"
        """
        if not hasattr(self.storage, "list_relationships_for_entity"):
            return ""
        if not entity_ids:
            return ""

        # Collect entity display names for readable output
        def _label(eid: str) -> str:
            try:
                note = self.storage.get_note_by_id(eid)
                if note:
                    return getattr(note, "title", None) or eid
            except Exception:
                pass
            return eid

        statements: List[str] = []
        seen_rel_ids: set = set()

        for entity_id in entity_ids:
            try:
                rels = self.storage.list_relationships_for_entity(entity_id, vault_id) or []
            except Exception:
                continue
            for rel in rels:
                if rel.id in seen_rel_ids:
                    continue
                seen_rel_ids.add(rel.id)
                src_label = _label(rel.source_id)
                tgt_label = _label(rel.target_id)
                rel_type = rel.label or rel.relationship_type
                if rel.direction == "bidirectional":
                    statements.append(f"{src_label} {rel_type} {tgt_label} (bidirectional)")
                else:
                    inv = get_inverse_label(rel.relationship_type)
                    statements.append(
                        f"{src_label} {rel_type} {tgt_label}"
                        f" (unidirectional → {tgt_label} {inv} {src_label})"
                    )

        if not statements:
            return ""
        return "Relationships: " + ", ".join(statements)

    @staticmethod
    def clear_cache():
        ContextAssembler._context_cache.clear()
        ContextAssembler._token_cache.clear()
