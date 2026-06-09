"""
RAGGraph retrieval for WorldStitch vault context.

Builds a structured context packet for each AI request by combining:
  - Vector similarity search (pgvector) on notes and characters
  - Graph walk along note_relationships from high-scoring nodes
  - The entity the user is currently viewing (always included)

Falls back to FTS (PostgreSQL full-text search) when embeddings are absent.
"""

import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import text

from server.embeddings import embed_text

logger = logging.getLogger(__name__)


# ── DB helpers (sync, run via asyncio.to_thread) ──────────────────────────────


def _vector_search_notes(engine, vault_id: str, query_vec: list[float], top_k: int) -> list[dict]:
    """Return top-K notes by cosine similarity. Skips deleted rows."""
    vec_literal = "[" + ",".join(str(x) for x in query_vec) + "]"
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, title, content, embedding <=> :vec AS distance "
                "FROM notes "
                "WHERE vault_id = :vid AND is_deleted = FALSE AND embedding IS NOT NULL "
                "ORDER BY distance ASC "
                "LIMIT :k"
            ),
            {"vec": vec_literal, "vid": vault_id, "k": top_k},
        ).fetchall()
    return [{"id": str(r[0]), "title": r[1] or "", "content": r[2] or "", "distance": float(r[3])} for r in rows]


def _fts_search_notes(engine, vault_id: str, query: str, top_k: int) -> list[dict]:
    """Full-text search fallback when embeddings are unavailable."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, title, content "
                "FROM notes "
                "WHERE vault_id = :vid AND is_deleted = FALSE "
                "AND (title ILIKE :q OR content ILIKE :q) "
                "LIMIT :k"
            ),
            {"vid": vault_id, "q": f"%{query[:100]}%", "k": top_k},
        ).fetchall()
    return [{"id": str(r[0]), "title": r[1] or "", "content": r[2] or "", "distance": 0.5} for r in rows]


def _vector_search_characters(engine, vault_id: str, query_vec: list[float], top_k: int) -> list[dict]:
    """Return top-K characters by cosine similarity."""
    vec_literal = "[" + ",".join(str(x) for x in query_vec) + "]"
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, data, embedding <=> :vec AS distance "
                "FROM characters "
                "WHERE vault_id = :vid AND embedding IS NOT NULL "
                "ORDER BY distance ASC "
                "LIMIT :k"
            ),
            {"vec": vec_literal, "vid": vault_id, "k": top_k},
        ).fetchall()
    results = []
    for r in rows:
        try:
            data = json.loads(r[1]) if r[1] else {}
        except Exception:
            data = {}
        results.append(
            {
                "id": str(r[0]),
                "name": data.get("name", ""),
                "description": data.get("description", "") or "",
                "distance": float(r[2]),
            }
        )
    return results


def _list_characters_fallback(engine, vault_id: str, top_k: int) -> list[dict]:
    """Fallback: return most recently saved characters when embeddings aren't available."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, data FROM characters WHERE vault_id = :vid LIMIT :k"),
            {"vid": vault_id, "k": top_k},
        ).fetchall()
    results = []
    for r in rows:
        try:
            data = json.loads(r[1]) if r[1] else {}
        except Exception:
            data = {}
        results.append(
            {
                "id": str(r[0]),
                "name": data.get("name", ""),
                "description": data.get("description", "") or "",
                "distance": 0.5,
            }
        )
    return results


def _fetch_relationships(engine, vault_id: str, entity_ids: list[str]) -> list[dict]:
    """Fetch typed edges where source or target is one of the given entity IDs."""
    if not entity_ids:
        return []
    placeholders = ", ".join(f":id{i}" for i in range(len(entity_ids)))
    params = {f"id{i}": eid for i, eid in enumerate(entity_ids)}
    params["vid"] = vault_id
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT source_id, target_id, relationship_type, label "
                f"FROM relationships "
                f"WHERE vault_id = :vid AND is_active = TRUE "
                f"AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))"
            ).bindparams(**params),
            params,
        ).fetchall()
    return [
        {
            "source_id": str(r[0]),
            "target_id": str(r[1]),
            "type": r[2] or "",
            "label": r[3] or "",
        }
        for r in rows
    ]


def _fetch_vault_summary(engine, vault_id: str) -> dict:
    """Return minimal vault metadata."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT data FROM vaults WHERE id = :vid"), {"vid": vault_id}).fetchone()
    if not row:
        return {"id": vault_id, "name": "", "description": ""}
    try:
        data = json.loads(row[0]) if row[0] else {}
    except Exception:
        data = {}
    return {
        "id": vault_id,
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "media_type": data.get("media_type", ""),
    }


def _note_by_id(engine, note_id: str) -> Optional[dict]:
    """Fetch a single note row by id."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, title, content FROM notes WHERE id = :nid"), {"nid": note_id}).fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "title": row[1] or "", "content": row[2] or ""}


def _character_by_id(engine, char_id: str) -> Optional[dict]:
    """Fetch a single character row by id."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, data FROM characters WHERE id = :cid"), {"cid": char_id}).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row[1]) if row[1] else {}
    except Exception:
        data = {}
    return {"id": str(row[0]), "name": data.get("name", ""), "description": data.get("description", "") or ""}


# ── Main build_context ────────────────────────────────────────────────────────


async def build_context(
    query: str,
    vault_id: str,
    current_entity: Optional[dict],
    mode: str,
    engine,
    api_key: Optional[str],
    top_k: int = 8,
) -> dict:
    """
    Build a structured vault context packet for an AI request.

    Returns:
        {
            "current_entity": {...} | None,
            "relevant_notes": [{id, title, snippet}],
            "relevant_characters": [{id, name, description}],
            "relationships": [{source_id, target_id, type, label}],
            "vault_summary": {id, name, description, media_type},
            "retrieval_trace": [{node_type, node_id, node_name, reason}],
        }
    """
    trace: list[dict] = []
    relevant_notes: list[dict] = []
    relevant_characters: list[dict] = []

    # 1. Embed the query (best-effort; None falls back to FTS)
    query_vec: Optional[list[float]] = None
    if api_key and query:
        try:
            query_vec = await embed_text(query, api_key)
        except Exception:
            logger.debug("build_context: embed_text failed, falling back to FTS")

    # 2. Vector or FTS search — run in thread since SA is sync
    if query_vec is not None:
        notes_raw = await asyncio.to_thread(_vector_search_notes, engine, vault_id, query_vec, top_k)
        chars_raw = await asyncio.to_thread(_vector_search_characters, engine, vault_id, query_vec, top_k)
        retrieval_method = "semantic match"
    else:
        notes_raw = await asyncio.to_thread(_fts_search_notes, engine, vault_id, query, top_k)
        chars_raw = await asyncio.to_thread(_list_characters_fallback, engine, vault_id, top_k)
        retrieval_method = "keyword match (embeddings not yet generated)"

    for n in notes_raw:
        snippet = n["content"][:300].rstrip()
        relevant_notes.append({"id": n["id"], "title": n["title"], "snippet": snippet})
        trace.append({"node_type": "note", "node_id": n["id"], "node_name": n["title"], "reason": retrieval_method})

    for c in chars_raw:
        desc_snippet = (c["description"] or "")[:200].rstrip()
        relevant_characters.append({"id": c["id"], "name": c["name"], "description": desc_snippet})
        trace.append({"node_type": "character", "node_id": c["id"], "node_name": c["name"], "reason": retrieval_method})

    # 3. Resolve current entity and always include it
    resolved_current: Optional[dict] = None
    if current_entity:
        etype = (current_entity.get("type") or "").lower()
        eid = current_entity.get("id", "")
        econtent = current_entity.get("content", "")

        if etype == "note" and eid:
            fetched = await asyncio.to_thread(_note_by_id, engine, eid)
            if fetched:
                resolved_current = {
                    "type": "note",
                    "id": eid,
                    "name": fetched["title"],
                    "content": fetched["content"],
                }
            else:
                # Trust what the frontend sent
                resolved_current = {"type": "note", "id": eid, "name": "", "content": econtent}

        elif etype == "character" and eid:
            fetched = await asyncio.to_thread(_character_by_id, engine, eid)
            if fetched:
                resolved_current = {
                    "type": "character",
                    "id": eid,
                    "name": fetched["name"],
                    "content": fetched["description"],
                }
            else:
                resolved_current = {"type": "character", "id": eid, "name": "", "content": econtent}

        else:
            resolved_current = {"type": etype, "id": eid, "name": "", "content": econtent}

        if resolved_current:
            trace.append(
                {
                    "node_type": resolved_current["type"],
                    "node_id": resolved_current["id"],
                    "node_name": resolved_current.get("name", ""),
                    "reason": "current entity (user is viewing this)",
                }
            )

        # Ensure the current entity's ID is in the top notes / chars if it's a note/char
        if etype == "note" and eid and not any(n["id"] == eid for n in relevant_notes):
            content = resolved_current.get("content", "") or ""
            relevant_notes.insert(
                0,
                {"id": eid, "title": resolved_current.get("name", ""), "snippet": content[:300]},
            )
        elif etype == "character" and eid and not any(c["id"] == eid for c in relevant_characters):
            desc = resolved_current.get("content", "") or ""
            relevant_characters.insert(
                0,
                {"id": eid, "name": resolved_current.get("name", ""), "description": desc[:200]},
            )

    # 4. Graph walk — fetch relationships from all retrieved entity IDs
    all_entity_ids = [n["id"] for n in relevant_notes] + [c["id"] for c in relevant_characters]
    if resolved_current and resolved_current.get("id"):
        cur_id = resolved_current["id"]
        if cur_id not in all_entity_ids:
            all_entity_ids.append(cur_id)

    relationships: list[dict] = []
    if all_entity_ids:
        try:
            relationships = await asyncio.to_thread(_fetch_relationships, engine, vault_id, all_entity_ids)
            for rel in relationships:
                trace.append(
                    {
                        "node_type": "relationship",
                        "node_id": f"{rel['source_id']}->{rel['target_id']}",
                        "node_name": rel["type"],
                        "reason": "relationship edge",
                    }
                )
        except Exception:
            logger.debug("build_context: relationship fetch failed", exc_info=True)

    # 5. Vault summary
    vault_summary: dict = {}
    try:
        vault_summary = await asyncio.to_thread(_fetch_vault_summary, engine, vault_id)
    except Exception:
        logger.debug("build_context: vault summary fetch failed", exc_info=True)
        vault_summary = {"id": vault_id, "name": "", "description": "", "media_type": ""}

    return {
        "current_entity": resolved_current,
        "relevant_notes": relevant_notes,
        "relevant_characters": relevant_characters,
        "relationships": relationships,
        "vault_summary": vault_summary,
        "retrieval_trace": trace,
    }


def format_context_for_prompt(context: dict) -> str:
    """
    Render the RAG context dict as a structured text block for injection
    into the AI system prompt.
    """
    lines: list[str] = []

    vault = context.get("vault_summary") or {}
    if vault.get("name"):
        lines.append(f"VAULT: {vault['name']}")
        if vault.get("description"):
            lines.append(vault["description"])
        lines.append("")

    current = context.get("current_entity")
    if current:
        lines.append("CURRENT CONTEXT:")
        lines.append(f'The user is viewing: {current.get("type", "unknown")} — "{current.get("name", "")}"')
        content = (current.get("content") or "")[:2000]
        if content:
            lines.append(content)
        lines.append("")

    notes = context.get("relevant_notes") or []
    if notes:
        lines.append("RELEVANT LORE:")
        for n in notes[:6]:
            snippet = (n.get("snippet") or "")[:300]
            lines.append(f"• [{n.get('title', 'Untitled')}] {snippet}")
        lines.append("")

    chars = context.get("relevant_characters") or []
    if chars:
        lines.append("KEY CHARACTERS:")
        for c in chars[:5]:
            desc = (c.get("description") or "")[:200]
            lines.append(f"• {c.get('name', 'Unknown')}: {desc}")
        lines.append("")

    rels = context.get("relationships") or []
    if rels:
        lines.append("RELATIONSHIPS:")
        for r in rels[:10]:
            label = f" ({r['label']})" if r.get("label") else ""
            lines.append(f"• {r['source_id']} → {r['target_id']}: {r['type']}{label}")
        lines.append("")

    return "\n".join(lines).strip()
