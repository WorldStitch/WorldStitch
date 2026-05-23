"""
AppEventBus — application-wide PyQt6 signal bus.

Usage
-----
Import the singleton accessor anywhere in the app:

    from WorldStitch.core.event_bus import get_event_bus
    get_event_bus().note_saved.connect(my_slot)
    get_event_bus().note_saved.emit("path/to/note.md")

The instance is created lazily on first access so this module is safe to
import before QApplication exists; the bus is only instantiated once
QApplication is running (i.e. on the first emit/connect call).
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

__all__ = ["AppEventBus", "get_event_bus"]


class AppEventBus(QObject):
    """Central signal bus — one instance shared across the whole application."""

    note_saved = pyqtSignal(str)           # vault-relative path
    note_deleted = pyqtSignal(str)         # vault-relative path
    note_moved = pyqtSignal(str, str)      # (src_path, dest_path)
    user_logged_in = pyqtSignal(str)       # user_id
    user_logged_out = pyqtSignal()
    vault_changed = pyqtSignal(str)        # vault_id


_instance: AppEventBus | None = None


def get_event_bus() -> AppEventBus:
    """Return the application-wide AppEventBus singleton."""
    global _instance
    if _instance is None:
        _instance = AppEventBus()
    return _instance
