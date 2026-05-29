# WorldStitch/ai/core/openai_engine.py
from typing import List, Tuple

from openai import OpenAI

from WorldStitch.ai.ai_logging import estimate_cost, log_api_call
from WorldStitch.ai.core.ai_base import AIInterface
from WorldStitch.ai.registry import register_plugin
from WorldStitch.config.config import Config


def count_tokens(text: str, model: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model(model)
    except Exception:
        from tiktoken import get_encoding

        enc = get_encoding("cl100k_base")
    return len(enc.encode(text))


@register_plugin("openai")
class OpenaiAI(AIInterface):
    """OpenAI backend for ChatCompletion-based tasks."""

    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.OPENAI_API_KEY
        self.model = config.COMPLETION_MODEL
        self.client = OpenAI(api_key=self.api_key)

    def update_api_key(self, new_key: str):
        self.api_key = new_key
        self.client = OpenAI(api_key=new_key)

    def update_models(self, embedding_model: str, completion_model: str):
        self.embedding_model = embedding_model
        self.model = completion_model

    def ask(self, prompt: str, system_prompt: str = "") -> Tuple[str, int, int]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        prompt_tokens = count_tokens((system_prompt + "\n" if system_prompt else "") + prompt, self.model) or 0
        try:
            resp = self.client.chat.completions.create(model=self.model, messages=messages)
            text = resp.choices[0].message.content.strip()
            resp_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
            cost = estimate_cost(self.model, prompt_tokens, resp_tokens)
            log_api_call(self.model, "ask", prompt_tokens, resp_tokens, cost, success=True)
            return text, prompt_tokens, resp_tokens
        except Exception as e:
            log_api_call(self.model, "ask", prompt_tokens or 0, 0, 0.0, success=False, error_msg=str(e))
            raise

    def summarize(self, text: str) -> Tuple[str, int, int]:
        try:
            prompt = f"Summarize the following note in one concise paragraph (up to 4 sentences):\n\n{text}"
            prompt_tokens = count_tokens(prompt, self.model) or 0
            resp = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}])
            summary = resp.choices[0].message.content.strip()
            resp_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
            cost = estimate_cost(self.model, prompt_tokens, resp_tokens)
            log_api_call(self.model, "summarize", prompt_tokens, resp_tokens, cost, success=True)
            return summary, prompt_tokens, resp_tokens
        except Exception:
            import traceback

            traceback.print_exc()
            raise

    def suggest_tags(self, text: str) -> Tuple[str, int, int]:
        prompt = "Suggest 3-7 descriptive tags (comma-separated) for this note:\n" + text
        prompt_tokens = count_tokens(prompt, self.model) or 0
        try:
            resp = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}])
            tags = resp.choices[0].message.content.strip()
            resp_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
            cost = estimate_cost(self.model, prompt_tokens, resp_tokens)
            log_api_call(self.model, "suggest_tags", prompt_tokens, resp_tokens, cost, success=True)
            return tags, prompt_tokens, resp_tokens
        except Exception as e:
            log_api_call(self.model, "suggest_tags", prompt_tokens or 0, 0, 0.0, success=False, error_msg=str(e))
            raise

    def propose_links(self, text: str, note_names: List[str]) -> Tuple[str, int, int]:
        options = ", ".join(note_names)
        prompt = f"Based on the note below, suggest internal links from the following list: {options}.\n" + text
        prompt_tokens = count_tokens(prompt, self.model) or 0
        try:
            resp = self.client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}])
            links = resp.choices[0].message.content.strip()
            resp_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
            cost = estimate_cost(self.model, prompt_tokens, resp_tokens)
            log_api_call(self.model, "propose_links", prompt_tokens, resp_tokens, cost, success=True)
            return links, prompt_tokens, resp_tokens
        except Exception as e:
            log_api_call(self.model, "propose_links", prompt_tokens or 0, 0, 0.0, success=False, error_msg=str(e))
            raise

    def update_max_tokens(self, max_tokens: int):
        self.max_tokens = max_tokens

    def search_context(self, query: str, top_k: int = 10) -> List[str]:
        raise RuntimeError(
            "OpenaiAI does not perform retrieval. Route 'search_context' through ModelRouter to the LoreAI backend."
        )
