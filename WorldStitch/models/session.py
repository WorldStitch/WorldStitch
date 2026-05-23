"""
Session model — tracks an authenticated user session.

Sessions are created on login and expire after a configurable duration.
They can be refreshed via a refresh token without requiring re-login.

Multiuser: each user can have multiple active sessions (different
devices/browsers). The storage layer enforces session limits if needed.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from pydantic import Field

from WorldStitch.models.base import CoreModel


class Session(CoreModel):
    """
    An authenticated user session.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel. owner_id is the authenticated user's ID.
    """

    expires_at: datetime = Field(..., description="UTC timestamp when this session expires.")
    refresh_token: Optional[str] = Field(default=None, description="Token used to extend the session.")
    ip_address: Optional[str] = Field(default=None, description="Client IP address at login.")
    user_agent: Optional[str] = Field(default=None, description="Client user-agent string.")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary session state (active vault, UI prefs, etc.).",
    )
    is_active: bool = Field(default=True, description="False once the session is logged out or expired.")

    def is_expired(self) -> bool:
        """Return True if the session has passed its expiry time."""
        return datetime.utcnow() >= self.expires_at

    def refresh_expiry(self, duration: timedelta) -> None:
        """Extend session expiry by the given duration."""
        self.expires_at = datetime.utcnow() + duration
