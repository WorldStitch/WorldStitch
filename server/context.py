"""
AppContext — the service locator handed to every route handler.

Slim replacement for the legacy WorldStitch.context.app_context version:
holds config, the async storage service, and the optional AI engine.
The old manager objects (ctx.users, ctx.notes, ...) are gone — routes
call ``ctx.storage`` directly. Per-request user identity is never stored
here; it travels as an ``Actor`` argument on storage calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from server.storage import AsyncStorage

if TYPE_CHECKING:
    from WorldStitch.ai.core.ai_base import AIInterface
    from WorldStitch.config.config import Config


class AppContext:
    """Central service locator — config, storage, and AI engine."""

    def __init__(self, config: "Config", storage: AsyncStorage):
        self.config = config
        self.storage = storage
        # AI engine — wired up by server/app.py after construction.
        self.ai: Optional["AIInterface"] = None

    def has_ai(self) -> bool:
        return self.ai is not None

    def require_ai(self) -> "AIInterface":
        if self.ai is None:
            raise RuntimeError("AI engine has not been initialised on AppContext.")
        return self.ai
