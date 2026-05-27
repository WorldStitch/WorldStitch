import uuid
from datetime import datetime
from typing import List, Optional

import bcrypt

from WorldStitch.models.user import User
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class UserManager:
    """
    Handles all business logic and storage operations for User entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_user(
        self,
        email: str,
        username: str,
        password: str,
        roles: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
    ) -> User:
        """
        Create and store a new user with hashed password.
        Raises ValueError if email already exists.
        """
        existing = self.storage.get_user_by_email(email)
        if existing:
            raise ValueError("Email already in use.")

        password_hash = self._hash_password(password)
        user_id = self._generate_id()
        user = User(
            id=user_id,
            owner_id=user_id,  # users own themselves
            email=email,
            username=username,
            password_hash=password_hash,
            roles=roles or ["player"],
            groups=groups or [],
            is_active=True,
            last_login=None,
        )
        self.storage.save_user(user)
        audit("update", "user", user.id, user_id=getattr(user, "owner_id", "system"))
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self.storage.get_user_by_id(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.storage.get_user_by_email(email)

    def update_user(self, user: User) -> None:
        """
        Update an existing user.
        """
        user.schema_version = max(user.schema_version, 1)
        if not user.last_login:
            user.last_login = datetime.utcnow()
        self.storage.save_user(user)
        audit("update", "user", user.id, user_id=getattr(user, "owner_id", "system"))

    def delete_user(self, user_id: str) -> None:
        """
        Soft-delete user by disabling account.
        """
        user = self.get_user(user_id)
        if user:
            user.is_active = False
            self.update_user(user)

    def hard_delete_user(self, user_id: str) -> None:
        """
        Permanently remove a user record from storage.
        Use with caution — this cannot be undone.
        """
        self.storage.delete_user_by_id(user_id)
        audit("delete", "user", user_id, user_id="system")

    def verify_password(self, password: str, password_hash: str) -> bool:
        """
        Check if a plaintext password matches the stored hash.
        """
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    def _hash_password(self, password: str) -> str:
        """
        Hash a plaintext password using bcrypt.
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _generate_id(self) -> str:
        """
        Generate a new UUID4 string.
        """
        return str(uuid.uuid4())

    def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        """
        Self-service password change.  Verifies the current password before
        applying the new one.  Raises ValueError on any validation failure.
        """
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found.")
        if not self.verify_password(current_password, user.password_hash):
            raise ValueError("Current password is incorrect.")
        if len(new_password) < 8:
            raise ValueError("New password must be at least 8 characters.")
        if current_password == new_password:
            raise ValueError("New password must be different from your current password.")
        user.password_hash = self._hash_password(new_password)
        self.update_user(user)
        audit("update", "user", user.id, user_id=user.id)

    def add_user_to_group(self, user_id: str, group_id: str) -> None:
        """
        Add a user to a group if not already a member.
        """
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found.")
        if group_id not in user.groups:
            user.groups.append(group_id)
            self.update_user(user)

    def remove_user_from_group(self, user_id: str, group_id: str) -> None:
        """
        Remove a user from a group if a member.
        """
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found.")
        if group_id in user.groups:
            user.groups.remove(group_id)
            self.update_user(user)

    def check_permission(self, user_id: str, permission: str) -> bool:
        """
        Placeholder for permission check logic.
        """
        user = self.get_user(user_id)
        if not user or not user.is_active:
            return False
        if "admin" in user.roles:
            return True
        # Extend this with actual permission checks later
        return False
