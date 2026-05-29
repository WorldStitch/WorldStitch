# WorldStitch/auth/auth_manager.py
"""
AuthManager — single point of entry for all authentication operations.

Consolidates login, logout, and auto-login so callers never need to touch
session_token.py or bcrypt directly.

Calls all callbacks registered on `session_ended` when logout completes.
"""

import logging
from typing import Optional

import bcrypt

from WorldStitch.auth.session_manager import SessionManager
from WorldStitch.models.user import User

logger = logging.getLogger(__name__)


class _SimpleSignal:
    """Minimal callable-list that mirrors pyqtSignal's connect/emit/disconnect API."""

    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def disconnect(self, callback=None):
        if callback is None:
            self._callbacks.clear()
        else:
            self._callbacks.remove(callback)

    def emit(self):
        for cb in self._callbacks:
            cb()


class AuthManager:
    """
    Owns the complete auth lifecycle: login, auto-login, logout.

    Parameters
    ----------
    storage : StorageBackend
        Shared storage instance (same one used by all managers).
    session_mgr : SessionManager
        Injected so callers can share a single SessionManager instance.
    """

    def __init__(self, storage, session_mgr: SessionManager) -> None:
        self._storage = storage
        self._sessions = session_mgr
        # Emitted after a successful logout so the app can return to LoginDialog.
        self.session_ended = _SimpleSignal()

    # ── Login ─────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate with email + password.

        Returns the User on success; None on invalid credentials.
        Does NOT create a session — call start_session() after.
        """
        user = self._storage.get_user_by_email(email)
        if not user or not user.is_active:
            logger.warning("Login failed for %r (not found or inactive)", email)
            return None

        try:
            if bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
                logger.info("Login success: %s (%s)", user.username, user.id)
                return user
        except Exception as exc:
            logger.warning("bcrypt error during login for %r: %s", email, exc)

        logger.warning("Login failed for %r (wrong password)", email)
        return None

    def auto_login(self) -> Optional[User]:
        """
        Attempt to restore a session from the on-disk token.
        Returns the User if the saved token is valid; otherwise None.
        """
        user = self._sessions.resolve_saved()
        if user:
            logger.info("Auto-login via session token: %s", user.username)
        return user

    def start_session(self, user: User) -> str:
        """
        Create a new session for user after a successful login.
        Returns the token string.
        """
        token = self._sessions.create(user)
        logger.info("Session started for %s (token prefix: %s…)", user.username, token[:8])
        return token

    # ── Logout ────────────────────────────────────────────────────────────

    def logout(self, user_id: Optional[str] = None) -> None:
        """
        Revoke the current session and fire session_ended callbacks.

        Parameters
        ----------
        user_id : str, optional
            If provided, ALL sessions for this user are revoked (log out everywhere).
            If omitted, only the on-disk token is revoked.
        """
        if user_id:
            self._sessions.revoke_all_for_user(user_id)
            logger.info("Logged out all sessions for user_id=%s", user_id)
        else:
            self._sessions.revoke_token_file()
            logger.info("Logged out (current token only)")

        self.session_ended.emit()
