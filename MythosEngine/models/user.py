"""
User model — an account in the MythosEngine system.

Users own vaults, notes, and all other resources. Authentication is
handled separately (auth module); this model only stores account state.
Passwords are always stored as hashes — never plaintext.

Multiuser: users belong to groups, carry roles, and are the root of
the permission hierarchy. Every CoreModel record references a user via
owner_id.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import EmailStr, Field

from MythosEngine.models.base import CoreModel


class User(CoreModel):
    """
    A user account.

    Inherits id, schema_version, owner_id, created_at, last_modified
    from CoreModel. For users, owner_id == id (a user owns themselves).
    """

    email: EmailStr = Field(..., description="Unique email address used for login.")
    username: str = Field(..., min_length=3, max_length=32, description="Display name.")
    password_hash: str = Field(..., min_length=10, description="Bcrypt/argon2 password hash. Never plaintext.")
    groups: List[str] = Field(default_factory=list, description="Group IDs this user belongs to.")
    roles: List[str] = Field(
        default_factory=list,
        description="System-level roles, e.g. ['admin', 'player']. Vault/campaign roles live in Group.",
    )
    system_role: str = Field(
        default="user",
        description="Platform-level role: owner | admin | moderator | tester | user | suspended",
    )
    is_active: bool = Field(default=True, description="False to disable login without deleting the account.")
    last_login: Optional[datetime] = Field(default=None, description="Timestamp of most recent login.")
