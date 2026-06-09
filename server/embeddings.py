"""
Embedding pipeline for WorldStitch vault content.

Provides fire-and-forget embedding of notes, characters, and maps into
pgvector columns so the RAG layer can do semantic similarity queries.

Key hierarchy (same as ai.py): user key → vault shared key → platform key.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def get_api_key_for_vault(vault_id: Optional[str], user, ctx) -> Optional[str]:
    """
    Resolve an OpenAI API key using the standard hierarchy:
      1. User's personal key
      2. Vault owner shared key (if vault_id provided and ai_key_shared)
      3. Platform OPENAI_API_KEY env var
    Returns None if no key is available anywhere.
    """
    store = getattr(ctx.storage, "user_api_keys", None)

    # 1. Personal key
    if store is not None:
        personal_key = store.get_personal_key(str(user.id))
        if personal_key:
            return personal_key

    # 2. Vault shared key
    if vault_id and hasattr(ctx.storage, "get_vault_ai_key"):
        try:
            vault = ctx.storage.get_vault_by_id(vault_id)
            if vault and getattr(vault, "ai_key_shared", False):
                vault_key = ctx.storage.get_vault_ai_key(vault_id)
                if vault_key:
                    return vault_key
        except Exception:
            logger.debug("Could not resolve vault AI key for vault_id=%s", vault_id)

    # 3. Platform key
    platform_key = os.environ.get("OPENAI_API_KEY", "")
    if platform_key:
        return platform_key

    return None


async def embed_text(text: str, api_key: str) -> Optional[list[float]]:
    """
    Embed a text string using text-embedding-3-small.
    Returns None on any failure — callers must handle a missing embedding gracefully.
    """
    if not text or not api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # model's practical token limit is ~8k tokens
        )
        return response.data[0].embedding
    except Exception:
        logger.debug("embed_text failed — embeddings will be skipped for this entity", exc_info=True)
        return None


async def _write_embedding(table: str, entity_id: str, embedding: list[float], engine) -> None:
    """Write an embedding vector to the specified table row (sync SA engine via thread)."""

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    vector_literal = "[" + ",".join(str(x) for x in embedding) + "]"

    def _do_write():
        with Session(engine) as session:
            session.execute(
                text(f"UPDATE {table} SET embedding = :vec::vector WHERE id = :id"),
                {"vec": vector_literal, "id": entity_id},
            )
            session.commit()

    await asyncio.to_thread(_do_write)


async def embed_entity(
    entity_type: str,
    entity_id: str,
    text_content: str,
    api_key: str,
    engine,
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
