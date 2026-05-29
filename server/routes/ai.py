"""
AI endpoints.

GET  /ai/status          — readiness check (no auth required)
POST /ai/ask             — ask the AI a question with vault context
POST /ai/ask/stream      — streaming SSE version of ask
POST /ai/summarize       — summarize text
POST /ai/suggest-tags    — suggest tags for text
POST /ai/propose-links   — propose internal wiki links for a note
GET  /ai/usage           — current-month token usage for the logged-in user

Key resolution order (most-to-least specific):
  1. User's own OpenAI key (stored in user_api_settings)
  2. Vault owner's key (if vault_id supplied and ai_key_shared is True)
  3. Platform key (if user's system_role is in PLATFORM_KEY_ROLES and key configured)
  4. Friendly 403 -- not a raw 503
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.analytics import track as analytics_track
from server.deps import PLATFORM_KEY_ROLES, get_ctx, get_current_user
from server.limiter import limiter
from WorldStitch.ai.cost_tracker import _DEFAULT_PRICING, _PRICING, AIUsageRecord
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.user import User


def _estimate_cost(ctx: AppContext, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost from token counts using configured model pricing."""
    model = getattr(ctx.config, "PREFERRED_MODEL", "") or "gpt-4o"
    prompt_rate, completion_rate = _PRICING.get(model, _DEFAULT_PRICING)
    return round((prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000, 8)


router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


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
    vault_id: Optional[str] = None


class SummarizeResponse(BaseModel):
    summary: str
    prompt_tokens: int
    completion_tokens: int


class SuggestTagsRequest(BaseModel):
    text: str
    existing_tags: list[str] = Field(default_factory=list)
    vault_id: Optional[str] = None


class SuggestTagsResponse(BaseModel):
    tags: list[str]
    prompt_tokens: int
    completion_tokens: int


class ProposeLinksRequest(BaseModel):
    text: str
    note_names: list[str] = Field(default_factory=list)
    vault_id: Optional[str] = None


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


def _build_vault_context(ctx: AppContext, vault_id: Optional[str], prompt: str) -> str:
    """Fetch recent notes from vault and prepend as context block."""
    if not vault_id:
        return prompt
    try:
        # Try semantic search first if index is ready
        if ctx.has_ai() and getattr(ctx.ai, "_index_ready", False):
            note_refs = ctx.ai.search_context(prompt, top_k=8)
            if note_refs:
                vault_notes_by_id = {}
                vault_notes_by_path = {}
                if hasattr(ctx.storage, "list_all_notes"):
                    for note in ctx.storage.list_all_notes(vault_id=vault_id):
                        note_id = getattr(note, "id", "") or ""
                        note_path = getattr(note, "path", "") or ""
                        if note_id:
                            vault_notes_by_id[note_id] = note
                        if note_path:
                            vault_notes_by_path[note_path] = note

                snippets = []
                for ref in note_refs:
                    note = vault_notes_by_id.get(ref) or vault_notes_by_path.get(ref)
                    if note is None and hasattr(ctx.storage, "get_note_by_id"):
                        candidate = ctx.storage.get_note_by_id(ref)
                        if candidate is not None and getattr(candidate, "vault_id", "") == vault_id:
                            note = candidate
                    if note is None:
                        continue
                    title = getattr(note, "title", "") or getattr(note, "path", "") or getattr(note, "id", "") or ""
                    content = (getattr(note, "content", "") or "")[:600]
                    if title or content:
                        snippets.append(f"## {title}\n{content}")

                if snippets:
                    context_block = "Relevant vault content:\n\n" + "\n\n---\n\n".join(snippets)
                    return context_block + "\n\n---\n\nUser question: " + prompt
        # Fallback: inject most recent notes
        notes = []
        if hasattr(ctx.storage, "list_all_notes"):
            notes = ctx.storage.list_all_notes(vault_id=vault_id)[:15]
        elif hasattr(ctx.storage, "list_notes"):
            note_paths = ctx.storage.list_notes(limit=15)
            if note_paths and hasattr(ctx.storage, "read_note"):
                for note_path in note_paths[:15]:
                    try:
                        note = ctx.storage.read_note(note_path)
                    except Exception:
                        continue
                    if note is not None:
                        notes.append(note)
        if notes:
            lines = ["Vault context (recent notes):"]
            for n in notes[:12]:
                if isinstance(n, dict):
                    title = n.get("title", "") or n.get("path", "") or n.get("id", "") or ""
                    content = (n.get("content", "") or "")[:600]
                else:
                    title = getattr(n, "title", "") or getattr(n, "path", "") or getattr(n, "id", "") or ""
                    content = (getattr(n, "content", "") or "")[:600]
                if not title and not content:
                    continue
                lines.append(f"## {title}\n{content}")
            if len(lines) > 1:
                context_block = "\n\n".join(lines)
                return context_block + "\n\n---\n\nUser question: " + prompt
    except Exception:
        logger.exception("Failed to build vault context")
    return prompt


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


def _make_engine_with_key(ctx: AppContext, api_key: str):
    """Return a fresh OpenaiAI instance configured with the given key."""
    from WorldStitch.ai.core.openai_engine import OpenaiAI

    engine = OpenaiAI(ctx.config)
    engine.update_api_key(api_key)
    return engine


def _get_ai_for_user(
    user_id: str,
    ctx: AppContext,
    vault_id: Optional[str] = None,
    user_system_role: str = "user",
):
    """
    Resolve an AI engine for this request using the key hierarchy:

    1. User personal key  -> fresh engine, no platform quota consumed
    2. Vault owner key    -> if vault_id supplied and ai_key_shared is True
    3. Platform key       -> if role is in PLATFORM_KEY_ROLES and ctx.has_ai()
    4. Friendly 403       -> clear message, never a raw 503

    Raises HTTP 429 if over monthly quota on the platform key.
    """
    store = getattr(ctx.storage, "user_api_keys", None)

    # 1. User own key
    if store is not None:
        personal_key = store.get_personal_key(user_id)
        if personal_key:
            return _make_engine_with_key(ctx, personal_key)

    # 2. Vault owner shared key
    if vault_id and hasattr(ctx.storage, "get_vault_ai_key"):
        try:
            vault = ctx.vaults.get_vault(vault_id)
            if vault and getattr(vault, "ai_key_shared", False):
                vault_key = ctx.storage.get_vault_ai_key(vault_id)
                if vault_key:
                    return _make_engine_with_key(ctx, vault_key)
        except Exception:
            logger.exception("Failed to resolve vault AI key for vault %s", vault_id)

    # 3. Platform key (privileged roles only)
    if user_system_role in PLATFORM_KEY_ROLES:
        if ctx.has_ai():
            if store is not None:
                store.check_and_increment(user_id)
            return ctx.require_ai()
        # Role qualifies but platform key is not configured on the server
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No platform AI key is configured on this server. "
                "Add your personal OpenAI key in Settings → AI, or ask the "
                "platform owner to set the OPENAI_API_KEY environment variable."
            ),
        )

    # 4. Regular user — no key available
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "No AI key is available. Add your OpenAI key in Settings → AI, "
            "or ask your vault owner to enable key sharing."
        ),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status")
async def ai_status(
    ctx: AppContext = Depends(get_ctx),
    authorization: Optional[str] = Header(default=None),
):
    """
    Platform AI readiness check.  Auth is optional — when a valid token is
    supplied the response also includes ``user_can_use_ai`` reflecting whether
    *this* user can actually make AI requests (personal key, platform key via
    privileged role, etc.).  Used by the frontend to suppress false-positive
    "AI not configured" banners for users who have a personal key configured.
    """
    platform_ready = ctx.has_ai()
    # Default: if the platform has a key, assume any authenticated user can use it
    user_can_use_ai = platform_ready

    if authorization and authorization.startswith("Bearer "):
        try:
            from server.auth_utils import decode_jwt

            token = authorization.removeprefix("Bearer ").strip()
            payload = decode_jwt(token)
            user_id = payload.get("sub")
            if user_id:
                store = getattr(ctx.storage, "user_api_keys", None)
                # Personal key → always works regardless of platform key
                if store is not None and store.get_personal_key(user_id):
                    user_can_use_ai = True
                elif platform_ready:
                    # Platform key present — only privileged roles may use it
                    user_obj = ctx.users.get_user(user_id)
                    role = getattr(user_obj, "system_role", "user") if user_obj else "user"
                    user_can_use_ai = role in PLATFORM_KEY_ROLES
                else:
                    user_can_use_ai = False
        except Exception:
            pass  # malformed token — fall back to platform_ready

    return {
        "ready": platform_ready,
        "user_can_use_ai": user_can_use_ai,
        "index_built": getattr(ctx.ai, "_index_ready", False) if platform_ready else False,
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
    """Ask the AI with optional conversation history."""
    try:
        _apply_preferred_model(ctx)
        ai = _get_ai_for_user(str(user.id), ctx, vault_id=req.vault_id, user_system_role=user.system_role)
        full_prompt = _build_vault_context(ctx, req.vault_id, _build_prompt_with_history(req.prompt, req.history))
        asyncio.create_task(analytics_track("ai.context_request", user_id=user.id, operation="ask"))
        ctx.analytics.track("ai.request_sent", user_id=user.id, data={"operation": "ask"})
        response, prompt_tokens, completion_tokens = ai.ask(full_prompt)
        cost_usd = _estimate_cost(ctx, prompt_tokens, completion_tokens)
        ctx.analytics.track(
            "ai.request_completed",
            user_id=user.id,
            data={
                "operation": "ask",
                "cost_usd": cost_usd,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )
        return AskResponse(response=response, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    except HTTPException:
        raise
    except Exception as e:
        ctx.analytics.track("ai.request_failed", user_id=user.id, data={"operation": "ask", "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"AI request failed: {str(e)}")


@router.post("/ask/stream")
async def stream_ask(
    req: AskRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Streaming SSE version of /ai/ask."""
    try:
        ai = _get_ai_for_user(str(user.id), ctx, vault_id=req.vault_id, user_system_role=user.system_role)
    except HTTPException:
        raise

    async def generate():
        try:
            full_prompt = _build_vault_context(ctx, req.vault_id, _build_prompt_with_history(req.prompt, req.history))
            response, _, _ = ai.ask(full_prompt)
            words = response.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Streaming AI ask failed")
            yield f"data: {json.dumps({'error': 'Request failed'})}\n\n"

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
        ai = _get_ai_for_user(str(user.id), ctx, vault_id=req.vault_id, user_system_role=user.system_role)
        summary, prompt_tokens, completion_tokens = ai.summarize(req.text)
        return SummarizeResponse(summary=summary, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Summarization failed: {str(e)}")


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
        ai = _get_ai_for_user(str(user.id), ctx, vault_id=req.vault_id, user_system_role=user.system_role)
        raw_tags, prompt_tokens, completion_tokens = ai.suggest_tags(req.text)
        tags = _parse_comma_list(raw_tags) if isinstance(raw_tags, str) else list(raw_tags)
        if req.existing_tags:
            existing_lower = {t.lower() for t in req.existing_tags}
            tags = [t for t in tags if t.lower() not in existing_lower]
        return SuggestTagsResponse(tags=tags, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Tag suggestion failed: {str(e)}"
        )


@router.post("/propose-links", response_model=ProposeLinksResponse)
@limiter.limit("20/minute")
async def propose_links(
    request: Request,
    req: ProposeLinksRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Suggest internal wiki links for the given note content."""
    try:
        ai = _get_ai_for_user(str(user.id), ctx, vault_id=req.vault_id, user_system_role=user.system_role)
        raw_links, prompt_tokens, completion_tokens = ai.propose_links(req.text, req.note_names)
        links = _parse_comma_list(raw_links) if isinstance(raw_links, str) else list(raw_links)
        if req.note_names:
            names_lower = {n.lower(): n for n in req.note_names}
            filtered = []
            for link in links:
                match = names_lower.get(link.lower())
                filtered.append(match if match else link)
            links = filtered
        seen = set()
        unique_links = []
        for lnk in links:
            if lnk.lower() not in seen:
                seen.add(lnk.lower())
                unique_links.append(lnk)
        return ProposeLinksResponse(
            links=unique_links, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Link proposal failed: {str(e)}")
