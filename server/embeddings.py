"""
Embedding pipeline for WorldStitch vault content.

Provides fire-and-forget embedding of notes, characters, and maps into
pgvector columns so the RAG layer can do semantic similarity queries.

Key hierarchy (same as ai.py): user key → vault shared key → platform key.
"""

import logging
import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


async def get_api_key_for_vault(vault_id: Optional[str], user, ctx) -> Optional[str]:
    """
    Resolve an OpenAI API key using the standard hierarchy:
      1. User's personal key
      2. Vault owner shared key (if vault_id provided and ai_key_shared)
      3. Platform OPENAI_API_KEY env var
    Returns None if no key is available anywhere.
    """
    from server.storage import Actor

    # 1. Personal key
    personal_key = await ctx.storage.get_personal_ai_key(str(user.id))
    if personal_key:
        return personal_key

    # 2. Vault shared key
    if vault_id:
        try:
            vault = await ctx.storage.get_vault_by_id(Actor.from_user(user), vault_id)
            if vault and getattr(vault, "ai_key_shared", False):
                vault_key = await ctx.storage.get_vault_ai_key(vault_id)
                if vault_key:
                    return vault_key
        except Exception:
            logger.debug("Could not resolve vault AI key for vault_id=%s", vault_id)

    # 3. Platform key
    platform_key = os.environ.get("OPENAI_API_KEY", "")
    if platform_key:
        return platform_key

    return None


async def embed_text(text_value: str, api_key: str) -> Optional[list[float]]:
    """
    Embed a text string using text-embedding-3-small.
    Returns None on any failure — callers must handle a missing embedding gracefully.
    """
    if not text_value or not api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text_value[:8000],  # model's practical token limit is ~8k tokens
        )
        return response.data[0].embedding
    except Exception:
        logger.debug("embed_text failed — embeddings will be skipped for this entity", exc_info=True)
        return None


async def _write_embedding(table: str, entity_id: str, embedding: list[float], engine: AsyncEngine) -> None:
    """Write an embedding vector to the specified table row."""
    vector_literal = "[" + ",".join(str(x) for x in embedding) + "]"
    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE {table} SET embedding = :vec::vector WHERE id = :id"),
            {"vec": vector_literal, "id": entity_id},
        )


async def embed_entity(
    entity_type: str,
    entity_id: str,
    text_content: str,
    api_key: str,
    engine: AsyncEngine,
) -> None:
    """
    Compute and store an embedding for a vault entity.

    entity_type must be one of: "notes", "characters", "maps"
    Designed to run as a fire-and-forget asyncio.create_task().
    Never raises — logs errors and returns silently.
    """
    valid_tables = {"notes", "characters", "maps"}
    if entity_type not in valid_tables:
        logger.warning("embed_entity: unknown entity_type=%s", entity_type)
        return

    try:
        vector = await embed_text(text_content, api_key)
        if vector is None:
            return
        await _write_embedding(entity_type, entity_id, vector, engine)
        logger.debug("Embedded %s id=%s", entity_type, entity_id)
    except Exception:
        logger.debug("embed_entity failed for %s id=%s", entity_type, entity_id, exc_info=True)
