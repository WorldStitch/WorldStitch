"""
VaultInvite model — an email-targeted invitation to join a specific vault.

The inviter sends an email with a signed link; the recipient follows the link
and (after logging in or registering) is added as a vault member.

Lifecycle:
  PENDING  →  ACCEPTED (accepted=True, accepted_by set)
           →  EXPIRED  (expires_at in the past)
           →  REVOKED  (is_active=False by inviter/admin)
"""

from datetime import datetime
from typing import Optional

from WorldStitch.models.base import CoreModel


class VaultInvite(CoreModel):
    """An email-targeted, vault-scoped invitation."""

    vault_id: str
    email: str
    token: str  # secrets.token_urlsafe(32) — used in the invite link

    invited_by: str  # user_id of the vault owner/admin who sent this

    expires_at: datetime  # default: now + 7 days
    is_active: bool = True

    accepted: bool = False
    accepted_by: Optional[str] = None  # user_id of who accepted

    def is_valid(self) -> bool:
        return self.is_active and not self.accepted and datetime.utcnow() < self.expires_at

    @property
    def status(self) -> str:
        if not self.is_active:
            return "revoked"
        if self.accepted:
            return "accepted"
        if datetime.utcnow() >= self.expires_at:
            return "expired"
        return "pending"
