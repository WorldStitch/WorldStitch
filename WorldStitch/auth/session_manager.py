# WorldStitch/auth/session_manager.py
"""
SessionManager — owns the full session lifecycle.

Responsibilities:
  - Create sessions (token generation + DB persistence + disk write)
  - Validate saved tokens (auto-login on startup)
  - Refresh expiry when a session is near expiry (<7 days left)
  - Revoke a single session or all sessions for a user
  - List all active sessions (for the admin panel)
"""

import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from WorldStitch.models.session import Session
from WorldStitch.models.user import User

_TOKEN_FILE = Path.home() / ".worldstitch_ai" / "session.token"
_EXPIRY_DAYS = 30
_REFRESH_THRESHOLD_DAYS = 7  # auto-extend if fewer than this many days remain


class SessionManager:
    """Manages session token creation, validation, refresh, and revocation."""

    def __init__(self, storage) -> None:
        self._storage = storage

    # ── Create ────────────────────────────────────────────────────────────

    def create(self, user: User) -> str:
        """
        Generate a new session token, persist it to the database and disk.
        Returns the token string.
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=_EXPIRY_DAYS)

        session = Session(
            id=token,
            owner_id=user.id,  # CoreModel required field
            expires_at=expires_at,
            context={"user_email": user.email, "username": user.username},
        )
        self._storage.save_session(session)
        self._write_token_file(token)
        return token

    # ── Validate (auto-login) ─────────────────────────────────────────────

    def resolve_saved(self) -> Optional[User]:
        """
        Read the saved token from disk, validate it, and return the owning User.
        Auto-refreshes expiry if within the refresh threshold.
        Returns None and clears the token if anything is invalid.
        """
        token = self._read_token_file()
        if not token:
            return None

        session = self._storage.get_session_by_id(token)
        if session is None or session.is_expired() or not session.is_active:
            self.revoke_token_file()
            return None

        user = self._storage.get_user_by_id(session.owner_id)
        if user is None or not user.is_active:
            self.revoke_token_file()
            return None

        # Auto-refresh if expiry is within the threshold window
        days_left = (session.expires_at - datetime.utcnow()).days
        if days_left < _REFRESH_THRESHOLD_DAYS:
            session.refresh_expiry(timedelta(days=_EXPIRY_DAYS))
            self._storage.save_session(session)

        return user

    # ── Revoke ────────────────────────────────────────────────────────────

    def revoke(self, token: str) -> None:
        """Mark a specific session as inactive in the DB."""
        session = self._storage.get_session_by_id(token)
        if session:
            session.is_active = False
            self._storage.save_session(session)

    def revoke_token_file(self) -> None:
        """
        Read and revoke the token currently saved on disk, then delete the file.
        Safe to call even if no file exists.
        """
        token = self._read_token_file()
        if token:
            self.revoke(token)
        _TOKEN_FILE.unlink(missing_ok=True)

    def revoke_all_for_user(self, user_id: str) -> None:
        """
        Invalidate every active session owned by user_id.
        Used for 'log out everywhere' and account disable.
        """
        for session in self.list_active():
            if session.owner_id == user_id:
                session.is_active = False
                self._storage.save_session(session)

        # Also clear local token file if it belongs to this user
        token = self._read_token_file()
        if token:
            s = self._storage.get_session_by_id(token)
            if s and s.owner_id == user_id:
                _TOKEN_FILE.unlink(missing_ok=True)

    # ── List ──────────────────────────────────────────────────────────────

    def list_active(self) -> List[Session]:
        """Return all non-expired, active sessions. Used by admin panel."""
        try:
            return self._storage.list_active_sessions()
        except Exception:
            return []

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _read_token_file() -> Optional[str]:
        if not _TOKEN_FILE.exists():
            return None
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        return token or None

    @staticmethod
    def _write_token_file(token: str) -> None:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(token, encoding="utf-8")
