"""
Server-side analytics helper — non-consent-gated, fire-and-forget event recording.

Route handlers call:
    import asyncio
    from server.analytics import track
    asyncio.create_task(track("note.created", user_id=user.id, vault_id=note.vault_id))

The function swallows all exceptions so analytics never impacts request latency.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def track(
    event_type: str,
    user_id: Optional[str] = None,
    vault_id: Optional[str] = None,
    session_id: Optional[str] = None,
    **properties: Any,
) -> None:
    """Record an analytics event directly to storage, bypassing consent checks."""
    try:
        from server.deps import get_ctx

        ctx = get_ctx()
        data: dict = dict(properties)
        if vault_id:
            data["vault_id"] = vault_id
        if session_id:
            data["session_id"] = session_id
        ctx.storage.save_analytics_event(user_id or "", event_type, data)
    except Exception:
        logger.debug("analytics.track silently failed: %s / %s", user_id, event_type)
