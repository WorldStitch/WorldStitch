"""
AppEventBus — application-wide signal bus (pure Python, no Qt dependency).

Usage
-----
Import the singleton accessor anywhere in the app:

    from WorldStitch.core.event_bus import get_event_bus
    get_event_bus().note_saved.connect(my_slot)
    get_event_bus().note_saved.emit("path/to/note.md")

The instance is created lazily on first access.
"""

from __future__ import annotations

from typing import Callable

__all__ = ["AppEventBus", "get_event_bus"]


class Signal:
    """Minimal signal that holds a list of callables and fires them on emit."""

    def __init__(self):
        self._slots: list[Callable] = []

    def connect(self, slot: Callable) -> None:
        if slot not in self._slots:
            self._slots.append(slot)

    def disconnect(self, slot: Callable) -> None:
        self._slots = [s for s in self._slots if s is not slot]

    def emit(self, *args, **kwargs) -> None:
        for slot in list(self._slots):
            try:
                slot(*args, **kwargs)
            except Exception:
                pass


class AppEventBus:
    """Central signal bus — one instance shared across the whole application."""

    def __init__(self):
        self.note_saved = Signal()       # vault-relative path
        self.note_deleted = Signal()     # vault-relative path
        self.note_moved = Signal()       # (src_path, dest_path)
        self.user_logged_in = Signal()   # user_id
        self.user_logged_out = Signal()
        self.vault_changed = Signal()    # vault_id


_instance: AppEventBus | None = None


def get_event_bus() -> AppEventBus:
    """Return the application-wide AppEventBus singleton."""
    global _instance
    if _instance is None:
        _instance = AppEventBus()
    return _instance
