"""
AI endpoints.

GET  /ai/status                  — readiness check (no auth required)
POST /ai/ask                     — ask the AI a question with vault context
POST /ai/ask/stream              — streaming SSE version of ask
POST /ai/summarize               — summarize text
POST /ai/suggest-tags            — suggest tags for text
POST /ai/propose-links           — propose internal wiki links for a note
GET  /ai/usage                   — current-month token usage for the logged-in user

GET  /ai/conversations/          — list saved conversations for active vault
POST /ai/conversations/          — create or update a saved conversation
GET  /ai/conversations/{id}      — fetch one saved conversation
DELETE /ai/conversations/{id}    — delete a saved conversation
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.analytics import track as analytics_track
from server.deps import PLATFORM_ADMIN, PLATFORM_KEY_ROLES, get_ctx, get_current_user
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

# ── AI mode addenda ────────────────────────────────────────────────────────────

_MODE_ADDENDA = {
    "lore": (
        "You are in **Lore Assistant** mode. Focus on world consistency, answer lore questions "
        "precisely, and actively suggest connections between entities in the vault. When answering, "
        "cite relevant notes when possible and flag any lore contradictions you notice."
    ),
    "writing": (
        "You are in **Writing Helper** mode. Focus on narrative craft, character voice, scene "
        "structure, and prose suggestions. Help the user write evocative descriptions, compelling "
        "dialogue, and strong scene arcs. Draw on vault lore to keep fiction consistent."
    ),
    "gm": (
        "You are in **GM Prep** mode. Focus on session planning, encounter design, NPC motivations, "
        "pacing, and player hooks. Help the GM prepare memorable moments, interesting complications, "
        "and satisfying session arcs grounded in the vault's existing lore."
    ),
    "developer": (
        "You are in **Developer** mode. You have full access to vault operations: creating, updating, "
        "listing, and deleting notes and folders. Help developers generate test data, seed the vault "
        "with sample content, inspect what exists, or clean up content. Be efficient and precise."
    ),
}

# ── Tool definitions ───────────────────────────────────────────────────────────

_TOOLS_ALL_MODES = [
    # ── Create ────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": (
                "Creates a new note in Browse with the given title and markdown content. "
                "Use this when the user asks you to create, write, or save a note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Markdown content for the note"},
                    "folder_path": {
                        "type": "string",
                        "description": "Name of the folder to put the note in. Use '/' for the root (no folder).",
                        "default": "/",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Creates a new folder in Browse.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Folder name"},
                    "parent_path": {
                        "type": "string",
                        "description": "Parent folder name. Use '/' for top-level.",
                        "default": "/",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_character",
            "description": "Creates a new character entry in the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Character name"},
                    "description": {"type": "string", "description": "Character description or backstory"},
                    "char_type": {
                        "type": "string",
                        "enum": ["npc", "player"],
                        "description": "Character type — npc or player",
                        "default": "npc",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the character",
                        "default": [],
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bulk_create_notes",
            "description": (
                "Creates multiple notes at once. Use this for generating test data, "
                "creating a set of related notes, or seeding a section of the vault."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notes": {
                        "type": "array",
                        "description": "Array of notes to create",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "folder_path": {
                                    "type": "string",
                                    "description": "Folder name or '/' for root",
                                    "default": "/",
                                },
                            },
                            "required": ["title", "content"],
                        },
                    }
                },
                "required": ["notes"],
            },
        },
    },
    # ── Read / Search ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": (
                "Search notes by keyword or title across the entire vault. "
                "Use this to find notes before reading or editing them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query — keywords or partial title"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note",
            "description": ("Read the full content of a specific note. Supply either the note_id or the exact title."),
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "ID of the note to read (preferred)"},
                    "title": {
                        "type": "string",
                        "description": "Title of the note to find (fallback if note_id unknown)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "List notes in the vault, optionally filtered by folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "Folder name to filter by, or omit for all notes",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return",
                        "default": 20,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_characters",
            "description": "List characters in the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of characters to return",
                        "default": 20,
                    },
                },
            },
        },
    },
    # ── Edit ─────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Updates an existing note's title, content, or tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "ID of the note to update"},
                    "title": {"type": "string", "description": "New title (omit to leave unchanged)"},
                    "content": {"type": "string", "description": "New content (omit to leave unchanged)"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Replacement tag list (omit to leave unchanged)",
                    },
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_tags",
            "description": "Add tags to a note without replacing the existing tag list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "ID of the note"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to add",
                    },
                },
                "required": ["note_id", "tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_note",
            "description": "Move a note to a different folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "ID of the note to move"},
                    "folder_path": {
                        "type": "string",
                        "description": "Destination folder name. Use '/' to move to root.",
                    },
                },
                "required": ["note_id", "folder_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_character",
            "description": "Update a character's name or description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string", "description": "ID of the character to update"},
                    "name": {"type": "string", "description": "New name (omit to leave unchanged)"},
                    "description": {"type": "string", "description": "New description (omit to leave unchanged)"},
                },
                "required": ["character_id"],
            },
        },
    },
    # ── Delete (requires confirmation) ────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": (
                "Delete a note. Call first with confirmed=false to get a confirmation prompt, "
                "then call again with confirmed=true once the user approves."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "ID of the note to delete"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true only after the user has confirmed the deletion",
                        "default": False,
                    },
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_character",
            "description": (
                "Delete a character. Call first with confirmed=false to get a confirmation prompt, "
                "then call again with confirmed=true once the user approves."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string", "description": "ID of the character to delete"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true only after the user has confirmed the deletion",
                        "default": False,
                    },
                },
                "required": ["character_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_folder",
            "description": (
                "Delete a folder. Call first with confirmed=false to get a confirmation prompt "
                "(it will warn you if the folder has sub-folders), "
                "then call again with confirmed=true once the user approves."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_id": {"type": "string", "description": "ID of the folder to delete (preferred)"},
                    "folder_path": {"type": "string", "description": "Name/path of the folder (fallback)"},
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true only after the user has confirmed the deletion",
                        "default": False,
                    },
                },
            },
        },
    },
    # ── Relationships ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_relationship",
            "description": (
                "Create a relationship edge between two vault entities (notes, characters, folders, etc.). "
                "relationship_type should describe the nature of the link, e.g. 'ally', 'enemy', 'created_by', 'located_in'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "ID of the source entity"},
                    "target_id": {"type": "string", "description": "ID of the target entity"},
                    "relationship_type": {"type": "string", "description": "Type/label of the relationship"},
                    "description": {
                        "type": "string",
                        "description": "Optional longer description of this relationship",
                    },
                },
                "required": ["source_id", "target_id", "relationship_type"],
            },
        },
    },
]

_TOOLS_DEVELOPER_EXTRA: list = []

# ── Canonical 4-tool set used by the _ask_with_tools loop ─────────────────────

_AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": ("Creates a new note in the vault with the given title and optional markdown content."),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title"},
                    "content": {"type": "string", "description": "Markdown content for the note"},
                    "folder_id": {
                        "type": "string",
                        "description": "ID of the folder to place the note in (omit for root)",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to attach to the note",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Creates a new folder in the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Folder name"},
                    "parent_id": {
                        "type": "string",
                        "description": "ID of the parent folder (omit for top-level)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description for the folder",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Updates an existing note's title, content, or tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "ID of the note to update"},
                    "title": {"type": "string", "description": "New title (omit to leave unchanged)"},
                    "content": {"type": "string", "description": "New content (omit to leave unchanged)"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (omit to leave unchanged)",
                    },
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Searches notes in the vault by semantic or keyword query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ============================================================================
# Request / Response models
# ============================================================================


class AskRequest(BaseModel):
    prompt: str
    vault_id: Optional[str] = None
    history: Optional[list[dict]] = None
    mode: Optional[str] = "lore"
    conversation_id: Optional[str] = None


class AskResponse(BaseModel):
    response: str
    prompt_tokens: int
    completion_tokens: int
    conversation_id: Optional[str] = None
    tool_results: Optional[list[dict]] = None


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


class ConversationMessage(BaseModel):
    role: str
    content: str
    tokens: Optional[int] = None
    cost: Optional[float] = None
    timestamp: Optional[str] = None


class SaveConversationRequest(BaseModel):
    vault_id: str
    title: Optional[str] = None
    messages: list[ConversationMessage]
    id: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    vault_id: str
    user_id: str
    title: str
    messages: list[dict]
    created_at: str
    updated_at: str


# ============================================================================
# Helpers
# ============================================================================


def _build_system_prompt(ctx: AppContext, user: User, vault_id: Optional[str], mode: Optional[str]) -> str:
    """
    Build the WorldStitch identity system prompt.
    Injected as a system message before every AI call — never skipped.
    """
    username = getattr(user, "username", None) or getattr(user, "email", "explorer")
    vault_name = "your vault"

    if vault_id:
        try:
            vault = ctx.storage.get_vault_by_id(vault_id)
            if vault:
                vault_name = vault.name
        except Exception:
            pass

    base = (
        f"You are the WorldStitch AI Assistant — a specialized worldbuilding companion built into "
        f"the WorldStitch platform. You are currently helping **{username}** with their vault called "
        f'**"{vault_name}"**. Your purpose is to help them develop their world, lore, characters, '
        f"stories, and campaign notes. You have access to their vault's notes and lore index to answer "
        f"questions about their world. Always respond as a knowledgeable worldbuilding assistant. "
        f"Never forget your role or act as a generic AI assistant."
    )

    tool_note = (
        " You have tools to take direct actions in the vault. When the user asks you to do something "
        "you MUST call the appropriate tool immediately — do not describe what you will do, just do it. "
        "\n\nAvailable tools:"
        "\n  CREATE: create_note, create_folder, create_character, bulk_create_notes"
        "\n  READ:   search_vault (keyword search), get_note (read full note by id or title),"
        "\n          list_notes (list notes, optional folder filter), list_characters"
        "\n  EDIT:   update_note (title/content/tags), add_tags (append tags without replacing),"
        "\n          move_note (change folder), update_character (name/description)"
        "\n  DELETE: delete_note, delete_character, delete_folder"
        "\n          — all delete tools require a two-step confirmation flow:"
        "\n            1) call with confirmed=false → returns a confirmation prompt"
        "\n            2) present the prompt to the user, then call again with confirmed=true"
        "\n  RELATE: create_relationship (link two entities with a typed edge)"
        "\n\nUse search_vault or list_notes to find a note before editing or deleting it. "
        "If asked to create multiple items, use bulk_create_notes or call create_note multiple times."
    )

    mode_key = (mode or "lore").lower()
    addendum = _MODE_ADDENDA.get(mode_key, _MODE_ADDENDA["lore"])
    return base + tool_note + "\n\n" + addendum


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
    """Fetch relevant notes from vault and prepend as context block."""
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

    # 3. Platform key — available to all authenticated roles in PLATFORM_KEY_ROLES
    #    (now includes "user" and "beta" so any account on an owner-keyed instance
    #    can use AI without needing to add their own key).
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


def _get_conversation_store(ctx: AppContext):
    """Return the conversation store from the storage backend, or None if unavailable."""
    return getattr(ctx.storage, "ai_conversations", None)


# ── Tool calling helpers ───────────────────────────────────────────────────────


def _get_tools_for_mode(mode: Optional[str], vault_id: Optional[str]) -> list:
    """Return OpenAI tool definitions for the given mode. Empty if no vault_id."""
    if not vault_id:
        return []
    tools = list(_TOOLS_ALL_MODES)
    if (mode or "").lower() == "developer":
        tools = tools + list(_TOOLS_DEVELOPER_EXTRA)
    return tools


def _resolve_folder_id(ctx: AppContext, vault_id: str, user: User, folder_path: str) -> Optional[str]:
    """Find or create a folder by name. Returns None for root ('/')."""
    if not folder_path or folder_path == "/":
        return None
    try:
        if hasattr(ctx.storage, "list_all_folders"):
            for folder in ctx.storage.list_all_folders(vault_id=vault_id):
                if folder.name == folder_path or getattr(folder, "path", "") == folder_path:
                    return folder.id
        # Not found — create it
        folder = ctx.folders.create_folder(
            vault_id=vault_id,
            name=folder_path,
            owner_id=user.id,
            parent_id=None,
        )
        return folder.id
    except Exception:
        logger.exception("Failed to resolve folder for path %s", folder_path)
        return None


def _set_user_ctx_for_tools(ctx: AppContext, user: User) -> None:
    """Set per-request user context so storage ACL checks use the right identity."""
    ctx.storage.set_user_context(
        user.id,
        is_admin=user.system_role in PLATFORM_ADMIN,
    )


def _execute_tool_call(
    tool_name: str,
    tool_args: dict,
    ctx: AppContext,
    vault_id: str,
    user: User,
) -> dict:
    """Execute a single AI tool call against the database. Returns a result dict."""
    logger.info("[tool] executing %s  args=%s", tool_name, tool_args)
    _set_user_ctx_for_tools(ctx, user)

    try:
        if tool_name == "create_note":
            title = tool_args.get("title", "Untitled")
            content = tool_args.get("content", "")
            tags = tool_args.get("tags") or ["ai-generated"]
            # Support both direct folder_id (from _AI_TOOLS) and folder_path (from _TOOLS_ALL_MODES)
            folder_id = tool_args.get("folder_id") or None
            if folder_id is None:
                folder_path = tool_args.get("folder_path", "/")
                folder_id = _resolve_folder_id(ctx, vault_id, user, folder_path)
            note = ctx.notes.create_note(
                vault_id=vault_id,
                owner_id=user.id,
                title=title,
                content=content,
                folder_id=folder_id,
                tags=tags,
            )
            return {"success": True, "note_id": note.id, "title": note.title}

        elif tool_name == "create_folder":
            name = tool_args.get("name", "New Folder")
            description = tool_args.get("description") or None
            # Support both direct parent_id (from _AI_TOOLS) and parent_path (from _TOOLS_ALL_MODES)
            parent_id = tool_args.get("parent_id") or None
            if parent_id is None:
                parent_path = tool_args.get("parent_path", "/")
                parent_id = (
                    _resolve_folder_id(ctx, vault_id, user, parent_path) if parent_path and parent_path != "/" else None
                )
            folder = ctx.folders.create_folder(
                vault_id=vault_id,
                name=name,
                owner_id=user.id,
                parent_id=parent_id,
                description=description,
            )
            return {"success": True, "folder_id": folder.id, "name": folder.name}

        elif tool_name == "update_note":
            note_id = tool_args.get("note_id")
            if not note_id:
                return {"success": False, "error": "note_id is required"}
            note = ctx.notes.get_note(note_id)
            if not note:
                return {"success": False, "error": f"Note {note_id} not found"}
            if getattr(note, "vault_id", None) and str(note.vault_id) != str(vault_id):
                return {"success": False, "error": f"Note {note_id} does not belong to this vault"}
            if tool_args.get("title") is not None:
                note.title = tool_args["title"]
            if tool_args.get("content") is not None:
                note.content = tool_args["content"]
            if tool_args.get("tags") is not None:
                note.tags = tool_args["tags"]
            ctx.notes.update_note(note, actor_id=str(user.id))
            return {"success": True, "note_id": note.id, "title": note.title}

        elif tool_name == "create_character":
            from WorldStitch.models.character import Character

            char = Character(
                id=str(uuid.uuid4()),
                vault_id=vault_id,
                campaign_id=vault_id,
                owner_id=user.id,
                name=tool_args.get("name", "Unknown"),
                description=tool_args.get("description") or None,
                is_npc=(tool_args.get("char_type", "npc") == "npc"),
                stats={},
                note_ids=[],
                meta={},
                ai_memory=None,
            )
            ctx.storage.save_character(char)
            return {"success": True, "character_id": char.id, "name": char.name}

        elif tool_name == "bulk_create_notes":
            notes_data = tool_args.get("notes", [])
            created = []
            for n in notes_data:
                folder_path = n.get("folder_path", "/")
                folder_id = _resolve_folder_id(ctx, vault_id, user, folder_path)
                note = ctx.notes.create_note(
                    vault_id=vault_id,
                    owner_id=user.id,
                    title=n.get("title", "Untitled"),
                    content=n.get("content", ""),
                    folder_id=folder_id,
                    tags=["ai-generated"],
                )
                created.append({"note_id": note.id, "title": note.title})
            return {"success": True, "created_count": len(created), "notes": created}

        elif tool_name == "search_vault":
            query = tool_args.get("query", "")
            limit = int(tool_args.get("limit", 10))
            if not query:
                return {"error": "query is required"}
            try:
                raw_results = ctx.storage.search_notes(query, vault_id=vault_id, top_k=limit)
                results = []
                for note in raw_results or []:
                    if isinstance(note, dict):
                        nid = note.get("id", "")
                        title = note.get("title", "")
                        content = note.get("content", "") or ""
                        folder_id = note.get("folder_id") or None
                        tags = note.get("tags") or []
                    else:
                        nid = getattr(note, "id", "")
                        title = getattr(note, "title", "")
                        content = getattr(note, "content", "") or ""
                        folder_id = getattr(note, "folder_id", None)
                        tags = getattr(note, "tags", []) or []
                    folder_name = None
                    if folder_id and hasattr(ctx.storage, "get_folder_by_id"):
                        try:
                            f = ctx.storage.get_folder_by_id(folder_id)
                            if f:
                                folder_name = f.name
                        except Exception:
                            pass
                    results.append(
                        {
                            "note_id": nid,
                            "title": title,
                            "folder": folder_name,
                            "excerpt": content[:300],
                        }
                    )
                return {"success": True, "results": results, "total": len(results)}
            except Exception as e:
                logger.exception("search_vault tool failed")
                return {"error": str(e)}

        elif tool_name == "get_note":
            note_id = tool_args.get("note_id")
            title_query = tool_args.get("title")
            note = None
            if note_id and hasattr(ctx.storage, "get_note_by_id"):
                note = ctx.storage.get_note_by_id(note_id)
            if note is None and title_query:
                try:
                    candidates = ctx.storage.search_notes(title_query, vault_id=vault_id, top_k=5)
                    for candidate in candidates or []:
                        if isinstance(candidate, dict):
                            if (candidate.get("title", "") or "").lower() == title_query.lower():
                                note = candidate
                                break
                        else:
                            if (getattr(candidate, "title", "") or "").lower() == title_query.lower():
                                note = candidate
                                break
                    if note is None and candidates:
                        note = candidates[0]
                except Exception:
                    logger.exception("get_note title search failed")
            if note is None:
                return {"success": False, "error": "Note not found"}
            if isinstance(note, dict):
                nid = note.get("id", "")
                t = note.get("title", "")
                content = note.get("content", "") or ""
                tags = note.get("tags") or []
                folder_id = note.get("folder_id") or None
            else:
                if getattr(note, "vault_id", None) and str(note.vault_id) != str(vault_id):
                    return {"success": False, "error": "Note does not belong to this vault"}
                nid = note.id
                t = getattr(note, "title", "")
                content = getattr(note, "content", "") or ""
                tags = getattr(note, "tags", []) or []
                folder_id = getattr(note, "folder_id", None)
            folder_name = None
            if folder_id and hasattr(ctx.storage, "get_folder_by_id"):
                try:
                    f = ctx.storage.get_folder_by_id(folder_id)
                    if f:
                        folder_name = f.name
                except Exception:
                    pass
            return {
                "success": True,
                "note_id": nid,
                "title": t,
                "content": content,
                "tags": tags,
                "folder": folder_name,
            }

        elif tool_name == "list_notes":
            folder_path = tool_args.get("folder_path")
            limit = int(tool_args.get("limit", 20))
            all_notes = []
            if hasattr(ctx.storage, "list_all_notes"):
                all_notes = ctx.storage.list_all_notes(vault_id=vault_id)
            # Filter by folder if specified
            if folder_path and folder_path != "/":
                folder_id_filter = _resolve_folder_id(ctx, vault_id, user, folder_path)
                if folder_id_filter:
                    all_notes = [
                        n for n in all_notes if str(getattr(n, "folder_id", "") or "") == str(folder_id_filter)
                    ]
            result = []
            for note in all_notes[:limit]:
                fid = getattr(note, "folder_id", None)
                folder_name = None
                if fid and hasattr(ctx.storage, "get_folder_by_id"):
                    try:
                        f = ctx.storage.get_folder_by_id(fid)
                        if f:
                            folder_name = f.name
                    except Exception:
                        pass
                result.append(
                    {
                        "note_id": note.id,
                        "title": getattr(note, "title", ""),
                        "folder": folder_name,
                        "tags": getattr(note, "tags", []) or [],
                    }
                )
            return {"success": True, "notes": result, "total": len(result)}

        elif tool_name == "list_characters":
            limit = int(tool_args.get("limit", 20))
            chars = ctx.storage.list_characters(vault_id=vault_id)
            result = []
            for char in chars[:limit]:
                result.append(
                    {
                        "character_id": char.id,
                        "name": getattr(char, "name", ""),
                        "description": getattr(char, "description", "") or "",
                    }
                )
            return {"success": True, "characters": result, "total": len(result)}

        elif tool_name == "add_tags":
            note_id = tool_args.get("note_id")
            new_tags = tool_args.get("tags") or []
            if not note_id:
                return {"success": False, "error": "note_id is required"}
            if not new_tags:
                return {"success": False, "error": "tags list is required"}
            note = ctx.notes.get_note(note_id)
            if not note:
                return {"success": False, "error": f"Note {note_id} not found"}
            if getattr(note, "vault_id", None) and str(note.vault_id) != str(vault_id):
                return {"success": False, "error": "Note does not belong to this vault"}
            for tag in new_tags:
                ctx.notes.add_tag(note_id, tag)
            note = ctx.notes.get_note(note_id)
            return {"success": True, "note_id": note_id, "tags": getattr(note, "tags", []) or []}

        elif tool_name == "move_note":
            note_id = tool_args.get("note_id")
            folder_path = tool_args.get("folder_path", "/")
            if not note_id:
                return {"success": False, "error": "note_id is required"}
            note = ctx.notes.get_note(note_id)
            if not note:
                return {"success": False, "error": f"Note {note_id} not found"}
            if getattr(note, "vault_id", None) and str(note.vault_id) != str(vault_id):
                return {"success": False, "error": "Note does not belong to this vault"}
            old_folder_id = getattr(note, "folder_id", None)
            new_folder_id = _resolve_folder_id(ctx, vault_id, user, folder_path)
            note.folder_id = new_folder_id
            ctx.notes.update_note(note, actor_id=str(user.id))
            # Update folder note_id lists
            try:
                if old_folder_id and hasattr(ctx.folders, "remove_note_from_folder"):
                    ctx.folders.remove_note_from_folder(old_folder_id, note_id)
                if new_folder_id and hasattr(ctx.folders, "add_note_to_folder"):
                    ctx.folders.add_note_to_folder(new_folder_id, note_id)
            except Exception:
                logger.exception("Failed to update folder note lists during move_note")
            return {"success": True, "note_id": note_id, "title": note.title, "new_folder_id": new_folder_id}

        elif tool_name == "update_character":
            character_id = tool_args.get("character_id")
            if not character_id:
                return {"success": False, "error": "character_id is required"}
            char = ctx.characters.get_character(character_id)
            if not char:
                return {"success": False, "error": f"Character {character_id} not found"}
            if getattr(char, "vault_id", None) and str(char.vault_id) != str(vault_id):
                return {"success": False, "error": "Character does not belong to this vault"}
            if tool_args.get("name") is not None:
                char.name = tool_args["name"]
            if tool_args.get("description") is not None:
                char.description = tool_args["description"]
            ctx.characters.update_character(char)
            return {"success": True, "character_id": char.id, "name": char.name}

        elif tool_name == "delete_note":
            note_id = tool_args.get("note_id")
            confirmed = bool(tool_args.get("confirmed", False))
            if not note_id:
                return {"success": False, "error": "note_id is required"}
            note = ctx.notes.get_note(note_id)
            if not note:
                return {"success": False, "error": f"Note {note_id} not found"}
            if getattr(note, "vault_id", None) and str(note.vault_id) != str(vault_id):
                return {"success": False, "error": "Note does not belong to this vault"}
            if not confirmed:
                return {
                    "requires_confirmation": True,
                    "message": f"Delete note '{note.title}'? This cannot be undone. Call delete_note again with confirmed=true to proceed.",
                    "note_id": note_id,
                }
            ctx.storage.soft_delete_note(note_id)
            return {"success": True, "deleted_note_id": note_id, "title": note.title}

        elif tool_name == "delete_character":
            character_id = tool_args.get("character_id")
            confirmed = bool(tool_args.get("confirmed", False))
            if not character_id:
                return {"success": False, "error": "character_id is required"}
            char = ctx.characters.get_character(character_id)
            if not char:
                return {"success": False, "error": f"Character {character_id} not found"}
            if getattr(char, "vault_id", None) and str(char.vault_id) != str(vault_id):
                return {"success": False, "error": "Character does not belong to this vault"}
            if not confirmed:
                return {
                    "requires_confirmation": True,
                    "message": f"Delete character '{char.name}'? This cannot be undone. Call delete_character again with confirmed=true to proceed.",
                    "character_id": character_id,
                }
            ctx.storage.soft_delete_character(character_id)
            return {"success": True, "deleted_character_id": character_id, "name": char.name}

        elif tool_name == "delete_folder":
            folder_id = tool_args.get("folder_id")
            folder_path = tool_args.get("folder_path")
            confirmed = bool(tool_args.get("confirmed", False))
            # Resolve folder
            folder = None
            if folder_id:
                folder = ctx.folders.get_folder(folder_id)
            if folder is None and folder_path:
                all_folders = ctx.storage.list_all_folders(vault_id=vault_id)
                for f in all_folders:
                    if f.name == folder_path or getattr(f, "path", "") == folder_path:
                        folder = f
                        break
            if folder is None:
                return {"success": False, "error": "Folder not found"}
            if getattr(folder, "vault_id", None) and str(folder.vault_id) != str(vault_id):
                return {"success": False, "error": "Folder does not belong to this vault"}
            resolved_id = folder.id
            if not confirmed:
                # Check for sub-folders
                child_count = 0
                try:
                    all_folders = ctx.storage.list_all_folders(vault_id=vault_id)
                    child_count = sum(
                        1 for f in all_folders if str(getattr(f, "parent_id", "") or "") == str(resolved_id)
                    )
                except Exception:
                    pass
                msg = f"Delete folder '{folder.name}'? This cannot be undone."
                if child_count:
                    msg += f" Warning: it contains {child_count} sub-folder(s)."
                return {
                    "requires_confirmation": True,
                    "message": msg + " Call delete_folder again with confirmed=true to proceed.",
                    "folder_id": resolved_id,
                }
            ctx.folders.delete_folder(resolved_id)
            return {"success": True, "deleted_folder_id": resolved_id, "name": folder.name}

        elif tool_name == "create_relationship":
            from WorldStitch.models.relationship import Relationship

            source_id = tool_args.get("source_id")
            target_id = tool_args.get("target_id")
            relationship_type = tool_args.get("relationship_type")
            description = tool_args.get("description") or None
            if not source_id or not target_id or not relationship_type:
                return {"success": False, "error": "source_id, target_id, and relationship_type are required"}
            rel = Relationship(
                vault_id=vault_id,
                owner_id=str(user.id),
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                label=description,
            )
            ctx.storage.create_relationship(rel)
            return {"success": True, "relationship_id": rel.id, "relationship_type": relationship_type}

        elif tool_name == "search_notes":
            query = tool_args.get("query", "")
            limit = int(tool_args.get("limit", 10))
            if not query:
                return {"error": "query is required"}
            try:
                raw_results = ctx.storage.search_notes(query, vault_id=vault_id, top_k=limit)
                notes_out = []
                for note in raw_results or []:
                    if isinstance(note, dict):
                        notes_out.append(
                            {
                                "id": note.get("id", ""),
                                "title": note.get("title", ""),
                                "content": (note.get("content", "") or "")[:300],
                            }
                        )
                    else:
                        notes_out.append(
                            {
                                "id": getattr(note, "id", ""),
                                "title": getattr(note, "title", ""),
                                "content": (getattr(note, "content", "") or "")[:300],
                            }
                        )
                return {"success": True, "notes": notes_out, "total": len(notes_out)}
            except Exception as e:
                logger.exception("search_notes tool failed")
                return {"error": str(e)}

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.exception("Tool call %s failed", tool_name)
        return {"success": False, "error": str(e)}


def _build_messages_for_tools(
    system_prompt: str,
    user_prompt_with_context: str,
    history: Optional[list[dict]],
) -> list:
    """Build a proper OpenAI messages array from system prompt, history, and user prompt."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for msg in history or []:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_prompt_with_context})
    return messages


def _make_tool_executor(ctx: AppContext, vault_id: str, user: User):
    """
    Return a synchronous callable that executes a named tool and returns a result
    dict.  Suitable as the ``tool_executor`` argument to engine.ask_with_tools().
    """
    _set_user_ctx_for_tools(ctx, user)

    def executor(tool_name: str, tool_args: dict) -> dict:
        return _execute_tool_call(tool_name, tool_args, ctx, vault_id, user)

    return executor


def _run_ask_with_tools(
    ai_engine,
    system_prompt: str,
    vault_prompt: str,
    history: Optional[list[dict]],
    tools: list,
    ctx: AppContext,
    vault_id: Optional[str],
    user: User,
) -> tuple:
    """
    Run one full tool-calling conversation and return
    (response_text, prompt_tokens, completion_tokens, tool_summaries).

    Delegates to engine.ask_with_tools() when available (covers both OpenaiAI
    directly and ModelRouter-wrapped engines).  Falls back to plain ask() when
    the engine does not support tools.
    """
    _vid = vault_id or ""

    if not tools or not hasattr(ai_engine, "ask_with_tools"):
        logger.info("[ai] no tools or engine lacks ask_with_tools — plain ask()")
        full = _build_prompt_with_history(vault_prompt, history)
        text, pt, ct = ai_engine.ask(full, system_prompt=system_prompt)
        return text, pt, ct, []

    logger.info("[ai] calling ask_with_tools with %d tool(s)", len(tools))
    executor = _make_tool_executor(ctx, _vid, user)

    text, pt, ct, calls = ai_engine.ask_with_tools(
        vault_prompt,
        system_prompt,
        tools,
        executor,
        history or [],
    )
    tool_summaries = [{"tool": c["name"], "result": c["result"]} for c in calls]
    logger.info(
        "[ai] ask_with_tools finished: %d tool call(s) made — %s",
        len(calls),
        [c["name"] for c in calls],
    )
    return text, pt, ct, tool_summaries


def _tool_status_label(tool_name: str, args: dict) -> str:
    """Return a human-readable status string for a tool call in progress."""
    if tool_name == "create_note":
        title = args.get("title", "note")
        return f'Creating note "{title}"…'
    elif tool_name == "create_folder":
        name = args.get("name", "folder")
        return f'Creating folder "{name}"…'
    elif tool_name == "update_note":
        return "Updating note…"
    elif tool_name == "create_character":
        name = args.get("name", "character")
        return f'Creating character "{name}"…'
    elif tool_name == "bulk_create_notes":
        count = len(args.get("notes", []))
        return f"Creating {count} notes…"
    elif tool_name == "search_vault":
        query = args.get("query", "")
        return f'Searching vault for "{query}"…'
    elif tool_name == "get_note":
        title = args.get("title") or args.get("note_id", "note")
        return f'Reading note "{title}"…'
    elif tool_name == "list_notes":
        return "Listing notes…"
    elif tool_name == "list_characters":
        return "Listing characters…"
    elif tool_name == "add_tags":
        return "Adding tags…"
    elif tool_name == "move_note":
        return "Moving note…"
    elif tool_name == "update_character":
        return "Updating character…"
    elif tool_name == "delete_note":
        return "Deleting note…"
    elif tool_name == "delete_character":
        return "Deleting character…"
    elif tool_name == "delete_folder":
        return "Deleting folder…"
    elif tool_name == "create_relationship":
        rel_type = args.get("relationship_type", "relationship")
        return f'Creating relationship "{rel_type}"…'
    return f"Running {tool_name}…"


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
    """Ask the AI with optional conversation history and tool-calling support."""
    try:
        _apply_preferred_model(ctx)
        ai_engine = _get_ai_for_user(str(user.id), ctx)
        system_prompt = _build_system_prompt(ctx, user, req.vault_id, req.mode)
        vault_prompt = _build_vault_context(ctx, req.vault_id, req.prompt)
        tools = _get_tools_for_mode(req.mode, req.vault_id)

        asyncio.create_task(analytics_track("ai.context_request", user_id=user.id, operation="ask"))
        ctx.analytics.track("ai.request_sent", user_id=user.id, data={"operation": "ask"})

        # Run blocking OpenAI calls in a thread so we don't stall the event loop.
        response, prompt_tokens, completion_tokens, tool_results = await asyncio.to_thread(
            _run_ask_with_tools,
            ai_engine,
            system_prompt,
            vault_prompt,
            req.history,
            tools,
            ctx,
            req.vault_id,
            user,
        )

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

        # Auto-save conversation to database
        conv_id = req.conversation_id
        try:
            store = _get_conversation_store(ctx)
            if store is not None and req.vault_id:
                user_msg = {
                    "role": "user",
                    "content": req.prompt,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                ai_msg = {
                    "role": "assistant",
                    "content": response,
                    "tokens": prompt_tokens + completion_tokens,
                    "cost": cost_usd,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                # Reconstruct full message list from history + new exchange
                existing_messages = list(req.history or [])
                existing_messages.append(user_msg)
                existing_messages.append(ai_msg)
                # Auto-title from first user message
                title = (req.prompt[:60] + "…") if len(req.prompt) > 60 else req.prompt
                conv_id = store.upsert(
                    conv_id=conv_id,
                    vault_id=req.vault_id,
                    user_id=str(user.id),
                    title=title,
                    messages=existing_messages,
                )
        except Exception:
            logger.exception("Failed to auto-save conversation")

        return AskResponse(
            response=response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            conversation_id=conv_id,
            tool_results=tool_results if tool_results else None,
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
    """Streaming SSE version of /ai/ask. Yields tool status events then response tokens."""
    try:
        ai_engine = _get_ai_for_user(str(user.id), ctx)
    except HTTPException:
        raise

    system_prompt = _build_system_prompt(ctx, user, req.vault_id, req.mode)

    async def generate():
        try:
            vault_prompt = _build_vault_context(ctx, req.vault_id, req.prompt)
            tools = _get_tools_for_mode(req.mode, req.vault_id)

            # ── Tool-calling path ──────────────────────────────────────────────
            # Uses ask_with_tools() which handles the full multi-round loop.
            # The blocking OpenAI calls run in a thread so the event loop stays
            # free.  We collect tool-status strings during execution via a
            # thread-safe queue and forward them as SSE events between polls.
            if tools and hasattr(ai_engine, "ask_with_tools"):
                import queue as _queue
                import threading as _threading

                status_q: _queue.SimpleQueue = _queue.SimpleQueue()
                _vid = req.vault_id or ""

                # Tool executor runs inside the worker thread; it pushes status
                # labels into the queue so we can forward them as SSE events.
                def _executor(tool_name: str, tool_args: dict) -> dict:
                    label = _tool_status_label(tool_name, tool_args)
                    status_q.put(("tool_status", label))
                    result = _execute_tool_call(tool_name, tool_args, ctx, _vid, user)
                    status_q.put(("tool_status", ""))
                    return result

                _set_user_ctx_for_tools(ctx, user)

                # Run the full conversation loop in a background thread.
                thread_result: dict = {}
                thread_exc: list = []
                done = _threading.Event()

                def _worker():
                    try:
                        thread_result["value"] = ai_engine.ask_with_tools(
                            vault_prompt,
                            system_prompt,
                            tools,
                            _executor,
                            req.history or [],
                        )
                    except Exception as exc:  # noqa: BLE001
                        thread_exc.append(exc)
                    finally:
                        done.set()

                _threading.Thread(target=_worker, daemon=True).start()

                # Poll: drain the status queue and yield events while the thread runs.
                _poll_start = asyncio.get_event_loop().time()
                while not done.is_set():
                    if asyncio.get_event_loop().time() - _poll_start > 60.0:
                        raise asyncio.TimeoutError()
                    await asyncio.sleep(0.05)
                    while not status_q.empty():
                        kind, payload = status_q.get_nowait()
                        yield f"data: {json.dumps({kind: payload})}\n\n"

                # Drain any remaining status events posted right before done.set()
                while not status_q.empty():
                    kind, payload = status_q.get_nowait()
                    yield f"data: {json.dumps({kind: payload})}\n\n"

                if thread_exc:
                    raise thread_exc[0]

                response, total_pt, total_ct, tool_calls_made = thread_result["value"]

                if tool_calls_made:
                    logger.info("[stream] tools ran: %s", [c["name"] for c in tool_calls_made])
                    yield f"data: {json.dumps({'tools_ran': True})}\n\n"

            else:
                # ── Fallback: regular ask (no tools) ──────────────────────────
                logger.info("[stream] no tools — plain ask()")
                full_prompt = _build_prompt_with_history(req.prompt, req.history)
                full_prompt = _build_vault_context(ctx, req.vault_id, full_prompt)
                response, total_pt, total_ct = await asyncio.wait_for(
                    asyncio.to_thread(ai_engine.ask, full_prompt, system_prompt=system_prompt),
                    timeout=60.0,
                )
                tool_calls_made = []

            # Stream the final response word-by-word
            words = response.split(" ")
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'token': token})}\n\n"

            # Auto-save streamed conversation
            try:
                store = _get_conversation_store(ctx)
                if store is not None and req.vault_id:
                    cost_usd = _estimate_cost(ctx, total_pt, total_ct)
                    user_msg = {
                        "role": "user",
                        "content": req.prompt,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    ai_msg = {
                        "role": "assistant",
                        "content": response,
                        "tokens": total_pt + total_ct,
                        "cost": cost_usd,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    existing_messages = list(req.history or [])
                    existing_messages.append(user_msg)
                    existing_messages.append(ai_msg)
                    title = (req.prompt[:60] + "…") if len(req.prompt) > 60 else req.prompt
                    conv_id = store.upsert(
                        conv_id=req.conversation_id,
                        vault_id=req.vault_id,
                        user_id=str(user.id),
                        title=title,
                        messages=existing_messages,
                    )
                    yield f"data: {json.dumps({'conversation_id': conv_id})}\n\n"
            except Exception:
                logger.exception("Failed to auto-save streamed conversation")

            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'error': 'Request cancelled'})}\n\n"
            yield "data: [DONE]\n\n"
            return
        except asyncio.TimeoutError:
            logger.warning("[stream] request timed out after 60 s")
            yield f"data: {json.dumps({'error': 'Request timed out — try again'})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Streaming AI ask failed")
            yield f"data: {json.dumps({'error': 'Request failed'})}\n\n"
            yield "data: [DONE]\n\n"

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
        ai_engine = _get_ai_for_user(str(user.id), ctx)
        summary, prompt_tokens, completion_tokens = ai_engine.summarize(req.text)

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
        ai_engine = _get_ai_for_user(str(user.id), ctx)
        raw_tags, prompt_tokens, completion_tokens = ai_engine.suggest_tags(req.text)

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
        ai_engine = _get_ai_for_user(str(user.id), ctx)
        raw_links, prompt_tokens, completion_tokens = ai_engine.propose_links(req.text, req.note_names)

        links = _parse_comma_list(raw_links) if isinstance(raw_links, str) else list(raw_links)

        if req.note_names:
            names_lower = {n.lower(): n for n in req.note_names}
            filtered = []
            for link in links:
                match = names_lower.get(link.lower())
                if match:
                    filtered.append(match)
                else:
                    filtered.append(link)
            links = filtered

        seen = set()
        unique_links = []
        for lnk in links:
            if lnk.lower() not in seen:
                seen.add(lnk.lower())
                unique_links.append(lnk)

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


# ============================================================================
# Conversation history endpoints
# ============================================================================


@router.get("/conversations/")
async def list_conversations(
    vault_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """List all saved AI conversations for a vault, newest first."""
    store = _get_conversation_store(ctx)
    if store is None:
        return []
    try:
        return store.list(vault_id=vault_id, user_id=str(user.id))
    except Exception as e:
        logger.warning("ai_conversations list failed (table may not exist yet): %s", e)
        return []


@router.post("/conversations/")
async def save_conversation(
    req: SaveConversationRequest,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Create or update a saved conversation."""
    store = _get_conversation_store(ctx)
    if store is None:
        raise HTTPException(status_code=503, detail="Conversation storage not available")
    try:
        title = req.title or (
            (req.messages[0].content[:60] + "…" if len(req.messages[0].content) > 60 else req.messages[0].content)
            if req.messages
            else "Untitled conversation"
        )
        conv_id = store.upsert(
            conv_id=req.id,
            vault_id=req.vault_id,
            user_id=str(user.id),
            title=title,
            messages=[m.model_dump() for m in req.messages],
        )
        return {"id": conv_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save conversation: {e}")


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Fetch a single saved conversation."""
    store = _get_conversation_store(ctx)
    if store is None:
        raise HTTPException(status_code=503, detail="Conversation storage not available")
    try:
        conv = store.get(conversation_id)
        if conv is None or conv.get("user_id") != str(user.id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch conversation: {e}")


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    ctx: AppContext = Depends(get_ctx),
    user: User = Depends(get_current_user),
):
    """Delete a saved conversation."""
    store = _get_conversation_store(ctx)
    if store is None:
        raise HTTPException(status_code=503, detail="Conversation storage not available")
    try:
        conv = store.get(conversation_id)
        if conv is None or conv.get("user_id") != str(user.id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        store.delete(conversation_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete conversation: {e}")
