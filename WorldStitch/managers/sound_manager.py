from datetime import datetime
from typing import Any, Dict, List, Optional

from WorldStitch.models.sound import Sound
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class SoundManager:
    """
    Handles all business logic and storage operations for Sound assets synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_sound(
        self,
        vault_id: str,
        owner_id: str,
        name: str,
        file_path: str,
        description: Optional[str] = None,
        group_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        linked_notes: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        is_public: bool = True,
    ) -> Sound:
        """
        Create and store a new sound asset.
        """
        sound = Sound(
            id=self._generate_id(),
            vault_id=vault_id,
            owner_id=owner_id,
            name=name,
            file_path=file_path,
            description=description,
            group_id=group_id,
            tags=tags or [],
            linked_notes=linked_notes or [],
            meta=meta or {},
            is_public=is_public,
            is_deleted=False,
            created_at=datetime.utcnow(),
            last_modified=datetime.utcnow(),
            schema_version=1,
            version=1,
        )
        self.storage.save_sound(sound)
        audit("update", "sound", sound.id, user_id=getattr(sound, "owner_id", "system"))
        return sound

    def get_sound(self, sound_id: str) -> Optional[Sound]:
        return self.storage.get_sound_by_id(sound_id)

    def update_sound(self, sound: Sound) -> None:
        sound.schema_version = max(sound.schema_version, 1)
        sound.version += 1
        sound.last_modified = datetime.utcnow()
        self.storage.save_sound(sound)
        audit("update", "sound", sound.id, user_id=getattr(sound, "owner_id", "system"))

    def delete_sound(self, sound_id: str) -> None:
        sound = self.get_sound(sound_id)
        if sound:
            sound.is_deleted = True
            self.update_sound(sound)

    def check_permission(self, sound_id: str, user_id: str, permission: str) -> bool:
        sound = self.get_sound(sound_id)
        if not sound:
            return False
        if "admin" in sound.permissions.get(user_id, ""):
            return True
        # Extend permission logic here
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
