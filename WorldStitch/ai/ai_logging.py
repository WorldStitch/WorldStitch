import csv
import os
from datetime import datetime
from pathlib import Path

# Update prices as needed. Default rates are for illustration only.
OPENAI_PRICES = {
    "gpt-3.5-turbo": 0.0015 / 1000,  # $0.0015 per 1K tokens
    "gpt-4": 0.03 / 1000,  # $0.03   per 1K tokens
}
DEFAULT_RATE = 0.002 / 1000  # fallback rate if model key missing

LOG_PATH = Path(__file__).parent / "ai_usage_log.csv"


def estimate_cost(model, prompt_tokens, completion_tokens):
    """
    Estimate OpenAI API call cost in USD.
    - Always returns a float. Never raises for bad inputs.
    """
    # Defensive: always default to something safe
    try:
        if model is None or not isinstance(model, str) or not model.strip():
            model = "gpt-3.5-turbo"  # fallback model name
        rate = OPENAI_PRICES.get(model, DEFAULT_RATE)
    except Exception:
        rate = DEFAULT_RATE

    try:
        pt = int(prompt_tokens) if prompt_tokens is not None else 0
    except Exception:
        pt = 0
    try:
        ct = int(completion_tokens) if completion_tokens is not None else 0
    except Exception:
        ct = 0

    try:
        return float(rate) * float(pt + ct)
    except Exception:
        return 0.0


def log_api_call(
    model,
    task,
    prompt_tokens,
    completion_tokens,
    cost,
    success=True,
    error_msg=None,
    prompt=None,
):
    """
    Append an API call record to the CSV log (with optional prompt text).
    - Coerces None tokens to 0.
    - Coerces None cost to 0.0.
    """
    exists = os.path.exists(LOG_PATH)

    # safe casts
    try:
        pt = int(prompt_tokens or 0)
    except Exception:
        pt = 0
    try:
        ct = int(completion_tokens or 0)
    except Exception:
        ct = 0
    safe_cost = cost if isinstance(cost, (int, float)) else 0.0

    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(
                [
                    "timestamp",
                    "model",
                    "task",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "cost_usd",
                    "success",
                    "error_msg",
                    "prompt",
                ]
            )
        writer.writerow(
            [
                datetime.now().isoformat(),
                model,
                task,
                pt,
                ct,
                pt + ct,
                round(safe_cost, 6),
                success,
                error_msg or "",
                prompt or "",
            ]
        )


def read_logs(n=20):
    """
    Read the last n log records as a list of dicts (most recent last).
    """
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        return rows[-n:] if n else rows


def count_tokens(text: str, model: str) -> int:
    """
    Count tokens via tiktoken, fallback to cl100k_base.
    """
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model(model)
    except Exception:
        from tiktoken import get_encoding

        enc = get_encoding("cl100k_base")
    return len(enc.encode(text))
