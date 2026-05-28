from datetime import datetime
from typing import Any, Dict, List, Optional

from WorldStitch.models.map import Map
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class MapManager:
    """
    Handles all business logic and storage operations for Map entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_map(
        self,
        vault_id: str,
        owner_id: str,
        name: str,
        file_path: str,
        description: Optional[str] = None,
        group_id: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
        tags: Optional[List[str]] = None,
        linked_notes: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Map:
        """
        Create and store a new map.
        """
        map_obj = Map(
            id=self._generate_id(),
            vault_id=vault_id,
            owner_id=owner_id,
            name=name,
            file_path=file_path,
            description=description,
            group_id=group_id,
            permissions=permissions or {},
            tags=tags or [],
            linked_notes=linked_notes or [],
            meta=meta or {},
            last_modified=datetime.utcnow(),
            created_at=datetime.utcnow(),
            schema_version=1,
            record_version=1,
        )
        self.storage.save_map(map_obj)
        audit("update", "map", map_obj.id, user_id=getattr(map_obj, "owner_id", "system"))
        return map_obj

    def get_map(self, map_id: str) -> Optional[Map]:
        return self.storage.get_map_by_id(map_id)

    def update_map(self, map_obj: Map) -> None:
        map_obj.schema_version = max(map_obj.schema_version, 1)
        map_obj.record_version += 1
        map_obj.last_modified = datetime.utcnow()
        self.storage.save_map(map_obj)
        audit("update", "map", map_obj.id, user_id=getattr(map_obj, "owner_id", "system"))

    def delete_map(self, map_id: str) -> None:
        map_obj = self.get_map(map_id)
        if map_obj:
            # Soft delete or permanent removal
            self.storage.delete_map_by_id(map_id)
            audit("delete", "map", map_id)

    def check_permission(self, map_id: str, user_id: str, permission: str) -> bool:
        map_obj = self.get_map(map_id)
        if not map_obj:
            return False
        if "admin" in map_obj.permissions.get(user_id, ""):
            return True
        # Extend permission logic here
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
