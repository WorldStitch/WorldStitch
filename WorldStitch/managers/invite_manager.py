# WorldStitch/managers/invite_manager.py
"""
InviteManager — CRUD and validation for invite codes.

An admin calls generate() to create a new code and share it out-of-band.
A prospective user enters it in SignupDialog; SignupDialog calls validate()
then the UserManager creates the account and calls redeem().
"""

import logging
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from WorldStitch.models.invite_code import InviteCode

logger = logging.getLogger(__name__)

_INVITE_EXPIRY_DAYS = 7


class InviteManager:
    """Manages invite code generation, validation, and redemption."""

    def __init__(self, storage) -> None:
        self._storage = storage

    # ── Generate ──────────────────────────────────────────────────────────

    def generate(self, created_by_user_id: str) -> InviteCode:
        """
        Create a fresh invite code with the default expiry (7 days).
        """
        return self.generate_with_expiry(created_by_user_id, expiry_days=_INVITE_EXPIRY_DAYS)

    def generate_with_expiry(self, created_by_user_id: str, expiry_days: int = _INVITE_EXPIRY_DAYS, max_uses: int = 1) -> InviteCode:
        """
        Create a fresh invite code with a configurable expiry and use limit.

        Parameters
        ----------
        created_by_user_id : str
            user_id of the admin generating this invite.
        expiry_days : int
            Number of days until the code expires (default: 7).
        max_uses : int
            Maximum number of times the code can be redeemed (default: 1).

        Returns
        -------
        InviteCode
            The newly created and persisted invite code object.
        """
        raw = secrets.token_urlsafe(9)  # 12 base64url chars
        # Format as XXXX-XXXX-XXXX (3 groups of 4) for readability
        raw = raw.upper().replace("-", "A").replace("_", "B")[:12]
        code_str = f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"

        invite = InviteCode(
            owner_id=created_by_user_id,
            code=code_str,
            created_by=created_by_user_id,
            expires_at=datetime.utcnow() + timedelta(days=expiry_days),
            max_uses=max_uses,
        )
        self._storage.save_invite(invite)
        logger.info(
            "Invite code generated: %s by user %s (expires in %d days, max_uses=%d)",
            code_str, created_by_user_id, expiry_days, max_uses,
        )
        return invite

    # ── Validate ──────────────────────────────────────────────────────────

    def validate(self, code_str: str) -> Optional[InviteCode]:
        """
        Look up a code and return the InviteCode if it is currently valid.
        Returns None if the code does not exist, is expired, revoked, or already used.
        """
        invite = self._storage.get_invite_by_code(code_str.strip().upper())
        if invite is None:
            return None
        return invite if invite.is_valid() else None

    # ── Redeem ────────────────────────────────────────────────────────────

    def redeem(self, code_str: str, used_by_user_id: str) -> bool:
        """
        Mark a code as used by used_by_user_id.

        Returns True on success, False if the code is no longer valid
        (race-condition guard).
        """
        invite = self._storage.get_invite_by_code(code_str.strip().upper())
        if invite is None or not invite.is_valid():
            return False

        invite.use_count += 1
        invite.used_by = used_by_user_id
        self._storage.save_invite(invite)
        logger.info("Invite %s redeemed by user %s", code_str, used_by_user_id)
        return True

    # ── Revoke ────────────────────────────────────────────────────────────

    def revoke(self, invite_id: str) -> None:
        """Admin-initiated revoke: set is_active=False so the code can't be used."""
        invite = self._storage.get_invite_by_id(invite_id)
        if invite:
            invite.is_active = False
            self._storage.save_invite(invite)
            logger.info("Invite %s revoked", invite_id)

    # ── List ──────────────────────────────────────────────────────────────

    def list_all(self) -> List[InviteCode]:
        """Return all invite codes (for admin panel), newest first."""
        try:
            codes = self._storage.list_invites()
            return sorted(codes, key=lambda c: c.created_at, reverse=True)
        except Exception:
            return []
