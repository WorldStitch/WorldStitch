from datetime import datetime
from typing import Dict, List, Optional

from WorldStitch.auth.permission_checker import permissions
from WorldStitch.models.note import Note
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.utils.audit_logger import audit


class NoteManager:
    """
    Handles all business logic and storage operations for Note entities synchronously.
    """

    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def create_note(
        self,
        vault_id: str,
        owner_id: str,
        title: str,
        content: str = "",
        folder_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        group_id: Optional[str] = None,
        permissions: Optional[Dict[str, str]] = None,
        links: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        ai_summary: Optional[str] = None,
        meta: Optional[Dict[str, str]] = None,
    ) -> Note:
        """
        Create and store a new note.
        """
        note = Note(
            owner_id=owner_id,
            vault_id=vault_id,
            title=title,
            content=content,
            folder_id=folder_id,
            tags=tags or [],
            group_id=group_id,
            permissions=permissions or {},
            links=links or [],
            attachments=attachments or [],
            ai_summary=ai_summary,
            meta=meta or {},
        )
        self.storage.save_note(note)
        audit("create", "note", note.id, user_id=owner_id)
        return note

    def get_note(self, note_id: str) -> Optional[Note]:
        return self.storage.get_note_by_id(note_id)

    def update_note(self, note: Note, actor_id: str = "system") -> None:
        permissions.require_write(note, actor_id)
        # Backup before overwriting so we can restore previous versions
        try:
            self.storage.backup_note(note.id)
        except Exception:
            pass  # backup failure must never block a save
        note.last_modified = datetime.utcnow()
        self.storage.save_note(note)
        audit("update", "note", note.id, user_id=note.owner_id)

    def delete_note(self, note_id: str, actor_id: str = "system") -> None:
        _note = self.get_note(note_id)
        if _note:
            permissions.require_delete(_note, actor_id)
        try:
            self.storage.backup_note(note_id)
        except Exception:
            pass
        self.storage.delete_note_by_id(note_id)
        audit("delete", "note", note_id, user_id=actor_id)

    def add_tag(self, note_id: str, tag: str) -> None:
        note = self.get_note(note_id)
        if note and tag not in note.tags:
            note.tags.append(tag)
            self.update_note(note)

    def remove_tag(self, note_id: str, tag: str) -> None:
        note = self.get_note(note_id)
        if note and tag in note.tags:
            note.tags.remove(tag)
            self.update_note(note)

    def check_permission(self, note_id: str, user_id: str, permission: str) -> bool:
        note = self.get_note(note_id)
        if not note:
            return False
        if "admin" in note.permissions.get(user_id, ""):
            return True
        # Extend permission logic here
        return False

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
