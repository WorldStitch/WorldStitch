from datetime import datetime
from typing import List, Optional

from WorldStitch.models.group import Group
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class GroupManager:
    """
    Handles all business logic and storage operations for Group entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_group(
        self,
        name: str,
        created_by: str,
        description: Optional[str] = None,
        members: Optional[List[str]] = None,
        member_roles: Optional[dict[str, str]] = None,
    ) -> Group:
        """
        Create and store a new group.
        """
        group = Group(
            id=self._generate_id(),
            name=name,
            owner_id=created_by,
            description=description,
            members=members or [],
            member_roles=member_roles or {},
            is_active=True,
            created_at=datetime.utcnow(),
            schema_version=1,
        )
        self.storage.save_group(group)
        audit("create", "group", group.id, user_id=getattr(group, "owner_id", "system"))
        return group

    def get_group(self, group_id: str) -> Optional[Group]:
        return self.storage.get_group_by_id(group_id)

    def update_group(self, group: Group) -> None:
        group.schema_version = max(group.schema_version, 1)
        self.storage.save_group(group)
        audit("update", "group", group.id, user_id=getattr(group, "owner_id", "system"))

    def delete_group(self, group_id: str) -> None:
        group = self.get_group(group_id)
        if group:
            group.is_active = False
            self.update_group(group)

    def add_member(self, group_id: str, user_id: str) -> None:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Group not found.")
        if user_id not in group.members:
            group.members.append(user_id)
            self.update_group(group)

    def remove_member(self, group_id: str, user_id: str) -> None:
        group = self.get_group(group_id)
        if not group:
            raise ValueError("Group not found.")
        if user_id in group.members:
            group.members.remove(user_id)
            self.update_group(group)

    def check_permission(self, group_id: str, user_id: str, permission: str) -> bool:
        group = self.get_group(group_id)
        if not group or not group.is_active:
            return False
        if group.owner_id == user_id:
            return True
        role = (group.member_roles or {}).get(user_id)
        if user_id in group.members and role in {"gm", permission}:
            return True
        # Extend with your permission rules
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
