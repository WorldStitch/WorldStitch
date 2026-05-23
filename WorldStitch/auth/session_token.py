"""
SessionToken — persistent login sessions stored on disk.

On successful login, a UUID token is generated, stored in the Session
table in SQLite, and saved to ~/.worldstitch_ai/session.token. On next
launch, the token file is checked and the user is auto-logged in if
the session is still valid.

Token file format: plain text, one line — just the UUID token.
"""

import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from WorldStitch.models.session import Session
from WorldStitch.models.user import User

_TOKEN_FILE = Path.home() / ".worldstitch_ai" / "session.token"
_TOKEN_EXPIRY_DAYS = 30


def create_session(user: User, storage) -> str:
    """
    Create a new session token for user, persist to DB and disk.
    Returns the token string.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=_TOKEN_EXPIRY_DAYS)

    session = Session(
        id=token,
        owner_id=user.id,
        expires_at=expires_at,
        context={"user_email": user.email, "username": user.username},
    )
    storage.save_session(session)

    # Persist token to disk
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(token, encoding="utf-8")

    return token


def resolve_saved_session(storage) -> Optional[User]:
    """
    Check for a saved token on disk. If valid and not expired,
    return the associated User. Otherwise clear the token and return None.
    """
    if not _TOKEN_FILE.exists():
        return None

    token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        return None

    session = storage.get_session_by_id(token)
    if session is None or session.is_expired() or not session.is_active:
        clear_session()
        return None

    user = storage.get_user_by_id(session.owner_id)
    if user is None or not user.is_active:
        clear_session()
        return None

    return user


def clear_session(storage=None) -> None:
    """
    Delete the saved token from disk and invalidate it in the DB.
    Called on logout or when session expires.
    """
    if _TOKEN_FILE.exists():
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        _TOKEN_FILE.unlink(missing_ok=True)

        if storage and token:
            session = storage.get_session_by_id(token)
            if session:
                session.is_active = False
                storage.save_session(session)
