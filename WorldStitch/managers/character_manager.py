from datetime import datetime
from typing import Any, Dict, List, Optional

from WorldStitch.models.character import Character
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class CharacterManager:
    """
    Handles all business logic and storage operations for Character entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_character(
        self,
        vault_id: str,
        owner_id: str,
        name: str,
        description: Optional[str] = None,
        group_id: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
        is_npc: bool = False,
        stats: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
        ai_memory: Optional[str] = None,
    ) -> Character:
        """
        Create and store a new character.
        """
        character = Character(
            id=self._generate_id(),
            vault_id=vault_id,
            owner_id=owner_id,
            name=name,
            description=description,
            group_id=group_id,
            permissions=permissions or {},
            is_npc=is_npc,
            stats=stats or {},
            tags=tags or [],
            note_ids=notes or [],
            meta=meta or {},
            ai_memory=ai_memory,
            last_modified=datetime.utcnow(),
            created_at=datetime.utcnow(),
            schema_version=1,
        )
        self.storage.save_character(character)
        return character

    def get_character(self, character_id: str) -> Optional[Character]:
        return self.storage.get_character_by_id(character_id)

    def update_character(self, character: Character) -> None:
        character.schema_version = max(character.schema_version, 1)
        character.version += 1
        character.last_modified = datetime.utcnow()
        self.storage.save_character(character)

    def delete_character(self, character_id: str) -> None:
        character = self.get_character(character_id)
        if character:
            # Soft delete if you want, or remove permanently
            self.storage.delete_character_by_id(character_id)
            audit("delete", "character", character_id)

    def check_permission(self, character_id: str, user_id: str, permission: str) -> bool:
        character = self.get_character(character_id)
        if not character:
            return False
        if "admin" in character.permissions.get(user_id, ""):
            return True
        # Extend permission logic here
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
