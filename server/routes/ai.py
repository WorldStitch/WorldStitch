"""
AI endpoints.

GET  /ai/status          — readiness check (no auth required)
POST /ai/ask             — ask the AI a question with vault context
POST /ai/ask/stream      — streaming SSE version of ask
POST /ai/summarize       — summarize text
POST /ai/suggest-tags    — suggest tags for text
POST /ai/propose-links   — propose internal wiki links for a note
GET  /ai/usage           — current-month token usage for the logged-in user
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from WorldStitch.ai.cost_tracker import AIUsageRecord, _DEFAULT_PRICING, _PRICING
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User

from server.analytics import track as analytics_track
from server.deps import get_ctx, get_current_user
from server.limiter import limiter


def _estimate_cost(ctx: AppContext, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts using configured model pricing."""
    model = getattr(ctx.config, "PREFERRED_MODEL", "") or "gpt-4o"
    prompt_rate, completion_rate = _PRICING.get(model, _DEFAULT_PRICING)
    return round((prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000, 8)


router = APIRouter(prefix="/ai", tags=["ai"])


# ============================================================================
# Request/Response models
# ============================================================================


class AskRequest(BaseModel):
    prompt: str
    vault_id: Optional[str] = None
    history: Optional[list[dict]] = None


class AskResponse(BaseModel):
    response: str
    prompt_tokens: int
    completion_tokens: int


class SummarizeRequest(BaseModel):
    text: str


class SummarizeResponse(BaseModel):
    summary: str
    prompt_tokens: int
    completion_tokens: int


class SuggestTagsRequest(BaseModel):
    text: str
    existing_tags: list[str] = Field(default_factory=list)


class SuggestTagsResponse(BaseModel):
    tags: list[str]
    prompt_tokens: int
    completion_tokens: int


class ProposeLinksRequest(BaseModel):
    text: str
    note_names: list[str] = Field(default_factory=list)


class ProposeLinksResponse(BaseModel):
    links: list[str]
    prompt_tokens: int
    completion_tokens: int


# ============================================================================
# Helpers
# ============================================================================


def _build_prompt_with_history(prompt: str, history: Optional[list[dict]]) -> str:
    """Prepend conversation history to the prompt if provided."""
    if not history:
        return prompt
    lines = []
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "Previous conversation:\n" + "\n".join(lines) + f"\n\nUser: {prompt}"


def _apply_preferred_model(ctx: AppContext) -> None:
    """Apply PREFERRED_MODEL from config to the AI engine if available."""
    preferred = getattr(ctx.config, "PREFERRED_MODEL", "") or ""
    if not preferred or not ctx.has_ai():
        return
    try:
        if hasattr(ctx.ai, "update_models"):
            embedding = getattr(ctx.config, "EMBEDDING_MODEL", "text-embedding-3-small")
            ctx.ai.update_models(embedding_model=embedding, completion_model=preferred)
    except Exception:
        pass


def _parse_comma_list(raw: str) -> list[str]:
    """Split a comma/newline-separated AI response into a clean list."""
    items = []
    for part in raw.replace("\n", ",").split(","):
        cleaned = part.strip().strip('"').strip("'").strip("*").strip("-").strip()
        if cleaned:
            items.append(cleaned)
    return items


def _get_ai_for_user(user_id: str, ctx: AppContext):
    """
    Return an AI engine instance appropriate for this user.

    - If the user has a personal OpenAI key stored, create a fresh engine
      instance using that key (no quota consumed).
    - Otherwise check + increment the user's monthly server-key quota, then
      return the shared ctx.ai engine.

    Raises HTTP 503 if no AI engine is configured, or HTTP 429 if the
    server-key quota is exceeded.
    """
    if not ctx.has_ai():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI engine not available",
        )

    store = getattr(ctx.storage, "user_api_keys", None)

    if store is not None:
        personal_key = store.get_personal_key(user_id)
        if personal_key:
            from WorldStitch.ai.core.openai_engine import OpenaiAI

            user_ai = OpenaiAI(ctx.config)
            user_ai.update_api_key(personal_key)
            return user_ai

        # No personal key — check and increment server-key quota (raises 429 if over limit)
        store.check_and_increment(user_id)

    return ctx.require_ai()


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status")
async def ai_status(ctx: AppContext = Depends(get_ctx)):
    return {
        "ready": ctx.has_ai(),
        "index_built": getattr(ctx.ai, "_index_ready", False) if ctx.has_ai() else False,
    }


@router.get("/usage")
async def ai_usage(
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Return the current-month AI usage summary for the logged-in user."""
    ct = ctx.cost_tracker
    if ct is None:
        return {"total_requests": 0, "total_tokens": 0, "estimated_cost": 0.0}

    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        with Session(ct.engine) as session:
            rows = session.scalars(
                select(AIUsageRecord).where(
                    AIUsageRecord.user_id == str(user.id),
                    AIUsageRecord.timestamp >= start_of_month,
                )
            ).all()
    except Exception:
        return {"total_requests": 0, "total_tokens": 0, "estimated_cost": 0.0}

    total_tokens = sum(r.total_tokens for r in rows)
    total_cost = sum(r.cost_usd for r in rows)
    return {
        "total_requests": len(rows),
        "total_tokens": total_tokens,
        "estimated_cost": round(total_cost, 6),
    }


@router.post("/ask", response_model=AskResponse)
@limiter.limit("20/minute")
async def ask(
    request: Request,
    req: AskRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Ask the AI with optional conversation history. Applies PREFERRED_MODEL if set."""
    try:
        _apply_preferred_model(ctx)
        ai = _get_ai_for_user(str(user.id), ctx)
        full_prompt = _build_prompt_with_history(req.prompt, req.history)
        asyncio.create_task(analytics_track("ai.context_request", user_id=user.id, operation="ask"))
        ctx.analytics.track("ai.request_sent", user_id=user.id, data={"operation": "ask"})
        response, prompt_tokens, completion_tokens = ai.ask(full_prompt)
        cost_usd = _estimate_cost(ctx, prompt_tokens, completion_tokens)
        ctx.analytics.track(
            "ai.request_completed",
            user_id=user.id,
            data={"operation": "ask", "cost_usd": cost_usd, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        )

        return AskResponse(
            response=response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except HTTPException:
        raise
    except Exception as e:
        ctx.analytics.track("ai.request_failed", user_id=user.id, data={"operation": "ask", "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI request failed: {str(e)}",
        )


@router.post("/ask/stream")
async def stream_ask(
    req: AskRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Streaming SSE version of /ai/ask. Yields tokens word-by-word."""
    # Resolve the AI client and check quota before entering the generator
    try:
        ai = _get_ai_for_user(str(user.id), ctx)
    except HTTPException:
        raise

    async def generate():
        try:
            full_prompt = _build_prompt_with_history(req.prompt, req.history)
            response, _, _ = ai.ask(full_prompt)

            words = response.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'token': token})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/summarize", response_model=SummarizeResponse)
@limiter.limit("20/minute")
async def summarize(
    request: Request,
    req: SummarizeRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Summarize the provided text."""
    try:
        ai = _get_ai_for_user(str(user.id), ctx)
        summary, prompt_tokens, completion_tokens = ai.summarize(req.text)

        return SummarizeResponse(
            summary=summary,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Summarization failed: {str(e)}",
        )


@router.post("/suggest-tags", response_model=SuggestTagsResponse)
@limiter.limit("20/minute")
async def suggest_tags(
    request: Request,
    req: SuggestTagsRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Suggest tags for text, filtering out existing ones."""
    try:
        ai = _get_ai_for_user(str(user.id), ctx)
        raw_tags, prompt_tokens, completion_tokens = ai.suggest_tags(req.text)

        # AI returns comma-separated string — parse to list
        tags = _parse_comma_list(raw_tags) if isinstance(raw_tags, str) else list(raw_tags)

        if req.existing_tags:
            existing_lower = {t.lower() for t in req.existing_tags}
            tags = [t for t in tags if t.lower() not in existing_lower]

        return SuggestTagsResponse(
            tags=tags,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tag suggestion failed: {str(e)}",
        )


@router.post("/propose-links", response_model=ProposeLinksResponse)
@limiter.limit("20/minute")
async def propose_links(
    request: Request,
    req: ProposeLinksRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Suggest internal [[wiki links]] for the given note content."""
    try:
        ai = _get_ai_for_user(str(user.id), ctx)
        raw_links, prompt_tokens, completion_tokens = ai.propose_links(
            req.text, req.note_names
        )

        links = _parse_comma_list(raw_links) if isinstance(raw_links, str) else list(raw_links)

        # Only keep links that match one of the provided note names (case-insensitive)
        if req.note_names:
            names_lower = {n.lower(): n for n in req.note_names}
            filtered = []
            for link in links:
                match = names_lower.get(link.lower())
                if match:
                    filtered.append(match)
                else:
                    # Include even if not exact match — AI may abbreviate
                    filtered.append(link)
            links = filtered

        # Deduplicate
        seen = set()
        unique_links = []
        for l in links:
            if l.lower() not in seen:
                seen.add(l.lower())
                unique_links.append(l)

        return ProposeLinksResponse(
            links=unique_links,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Link proposal failed: {str(e)}",
        )
