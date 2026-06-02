from datetime import datetime
from typing import Dict, List, Optional

from WorldStitch.models.folder import Folder
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class FolderManager:
    """
    Handles all business logic and storage operations for Folder entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_folder(
        self,
        vault_id: str,
        owner_id: str,
        name: str,
        parent_id: Optional[str] = None,
        description: Optional[str] = None,
        group_id: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
        note_ids: Optional[List[str]] = None,
        meta: Optional[Dict[str, str]] = None,
    ) -> Folder:
        """
        Create and store a new folder.
        """
        folder = Folder(
            id=self._generate_id(),
            vault_id=vault_id,
            owner_id=owner_id,
            name=name,
            parent_id=parent_id,
            description=description,
            group_id=group_id,
            permissions=permissions or {},
            note_ids=note_ids or [],
            meta=meta or {},
            last_modified=datetime.utcnow(),
            created_at=datetime.utcnow(),
            schema_version=1,
            record_version=1,
        )
        self.storage.save_folder(folder)
        return folder

    def get_folder(self, folder_id: str) -> Optional[Folder]:
        return self.storage.get_folder_by_id(folder_id)

    def update_folder(self, folder: Folder) -> None:
        folder.schema_version = max(folder.schema_version, 1)
        folder.record_version += 1
        folder.last_modified = datetime.utcnow()
        self.storage.save_folder(folder)

    def delete_folder(self, folder_id: str) -> None:
        folder = self.get_folder(folder_id)
        if folder:
            # Soft delete: implement is_deleted in model if needed
            # For now, remove permanently
            self.storage.delete_folder_by_id(folder_id)
            audit("delete", "folder", folder_id)

    def add_note_to_folder(self, folder_id: str, note_id: str) -> None:
        folder = self.get_folder(folder_id)
        if folder and note_id not in folder.note_ids:
            folder.note_ids.append(note_id)
            self.update_folder(folder)

    def remove_note_from_folder(self, folder_id: str, note_id: str) -> None:
        folder = self.get_folder(folder_id)
        if folder and note_id in folder.note_ids:
            folder.note_ids.remove(note_id)
            self.update_folder(folder)

    def check_permission(self, folder_id: str, user_id: str, permission: str) -> bool:
        folder = self.get_folder(folder_id)
        if not folder:
            return False
        if "admin" in folder.permissions.get(user_id, ""):
            return True
        # Extend permission logic here
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
