"""
AnalyticsTracker — consent-gated event recording for WorldStitch.

All tracking is silently skipped unless the user has explicitly opted in.
Never raises: exceptions are caught so tracking never breaks application flow.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from WorldStitch.storage.storage_base import StorageBackend


class AnalyticsTracker:
    """
    Lightweight wrapper around analytics storage methods.

    Parameters
    ----------
    storage : StorageBackend
        The active storage backend (must implement the analytics_* methods).
    app_version : str
        Current application version string — included in every event.
    """

    def __init__(self, storage: "StorageBackend", app_version: str = "") -> None:
        self._storage = storage
        self._app_version = app_version

    def track(
        self,
        event_type: str,
        user_id: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an analytics event if the user has consented.

        Silently no-ops when:
        - user_id is empty
        - the user has not granted analytics consent
        - any storage error occurs
        """
        if not user_id:
            return
        try:
            if not self._storage.user_has_analytics_consent(user_id):
                return
            payload = dict(data or {})
            if self._app_version:
                payload.setdefault("app_version", self._app_version)
            self._storage.save_analytics_event(user_id, event_type, payload)
        except Exception:
            logger.debug("analytics.track silently failed for %s / %s", user_id, event_type)
