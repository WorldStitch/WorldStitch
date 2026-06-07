"""
Integration tests for AI routes.

Notes:
- test_ai_no_key: returns 503 as specified.  _get_ai_for_user() raises
  HTTP 503 "AI engine not available" when ctx.has_ai() is False.
  The conftest deliberately leaves OPENAI_API_KEY="" so ctx.ai stays None.

- test_ai_missing_prompt (renamed from test_ai_requires_vault):
  vault_id is Optional[str] = None in AskRequest — omitting it is valid and
  produces no 422.  The only required field is `prompt`.  Sending an empty
  body (missing `prompt`) triggers FastAPI's request-validation 422.
"""


# ---------------------------------------------------------------------------
# POST /ai/ask — auth gate
# ---------------------------------------------------------------------------


def test_ai_requires_auth(client):
    """POST /ai/ask without an Authorization header returns 401."""
    res = client.post("/ai/ask", json={"prompt": "Hello"})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# POST /ai/ask — request-validation gate
# ---------------------------------------------------------------------------


def test_ai_missing_prompt(client, auth_headers):
    """POST /ai/ask with no body (missing required `prompt`) returns 422.

    Note: vault_id is Optional in AskRequest, so omitting it alone is not
    an error.  Only the required `prompt` field triggers 422 when absent.
    """
    res = client.post("/ai/ask", json={}, headers=auth_headers)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# POST /ai/ask — no AI key configured
# ---------------------------------------------------------------------------


def test_ai_no_key(client, auth_headers):
    """POST /ai/ask when no OpenAI key is configured returns 503.

    _get_ai_for_user() raises HTTP 503 "AI engine not available" when
    ctx.has_ai() is False.  The conftest leaves OPENAI_API_KEY="" so ctx.ai
    is never initialised, triggering this path on every /ai/ask request.
    """
    res = client.post(
        "/ai/ask",
        json={"prompt": "Tell me about my world."},
        headers=auth_headers,
    )
    assert res.status_code == 503
    detail = res.json()["detail"]
    # Detail should describe the problem, not be a raw traceback
    assert "ai" in detail.lower() or "engine" in detail.lower() or "available" in detail.lower()
