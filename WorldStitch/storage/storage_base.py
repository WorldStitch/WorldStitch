from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Set

if TYPE_CHECKING:
    from WorldStitch.search.search_types import SearchQuery, SearchResult

from WorldStitch.models.character import Character
from WorldStitch.models.folder import Folder
from WorldStitch.models.group import Group
from WorldStitch.models.image import Image
from WorldStitch.models.invite_code import InviteCode
from WorldStitch.models.map import Map
from WorldStitch.models.note import Note
from WorldStitch.models.relationship import Relationship
from WorldStitch.models.session import Session
from WorldStitch.models.sound import Sound
from WorldStitch.models.user import User
from WorldStitch.models.vault import Vault


class StorageBackend(ABC):
    """
    Abstract storage interface.

    User context
    ------------
    Call set_user_context(user_id, is_admin) immediately after login.
    All list/get methods use this to enforce data isolation:
      - Admins see everything.
      - Regular users see only records they own, records in vaults they
        belong to, or records explicitly shared with them via permissions.
    """

    # Populated by set_user_context() after login
    _current_user_id: Optional[str] = None
    _is_admin: bool = False

    def set_user_context(self, user_id: str, is_admin: bool = False) -> None:
        """
        Set the active user for all subsequent queries.
        Must be called once after login before any data access.
        """
        self._current_user_id = user_id
        self._is_admin = is_admin

    def _can_access(self, owner_id: str, permissions: dict, member_ids: list | None = None) -> bool:
        """
        Return True if the current user may access a resource.

        Rules (in order):
          1. Admins always have access.
          2. The owner always has access.
          3. Explicit permissions entry grants access.
          4. Vault membership grants access (pass vault.members as member_ids).
          5. Default: deny.
        """
        if self._is_admin:
            return True
        uid = self._current_user_id
        if not uid:
            return False
        if uid == owner_id:
            return True
        if uid in permissions:
            return True
        get_subjects = getattr(self, "_permission_subject_ids", None)
        if callable(get_subjects):
            subjects = get_subjects()
            if any(subject in permissions for subject in subjects):
                return True
        if member_ids and uid in member_ids:
            return True
        return False

    # --- CRUD for ALL MODELS ---
    @abstractmethod
    def save_user(self, user: User) -> None:
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        pass

    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    def delete_user_by_id(self, user_id: str) -> None:
        pass

    @abstractmethod
    def save_group(self, group: Group) -> None:
        pass

    @abstractmethod
    def get_group_by_id(self, group_id: str) -> Optional[Group]:
        pass

    @abstractmethod
    def delete_group_by_id(self, group_id: str) -> None:
        pass

    @abstractmethod
    def save_vault(self, vault: Vault) -> None:
        pass

    @abstractmethod
    def get_vault_by_id(self, vault_id: str) -> Optional[Vault]:
        pass

    @abstractmethod
    def delete_vault_by_id(self, vault_id: str) -> None:
        pass

    @abstractmethod
    def save_folder(self, folder: Folder) -> None:
        pass

    @abstractmethod
    def get_folder_by_id(self, folder_id: str) -> Optional[Folder]:
        pass

    @abstractmethod
    def delete_folder_by_id(self, folder_id: str) -> None:
        pass

    @abstractmethod
    def save_note(self, note: Note) -> None:
        pass

    @abstractmethod
    def get_note_by_id(self, note_id: str) -> Optional[Note]:
        pass

    @abstractmethod
    def delete_note_by_id(self, note_id: str) -> None:
        pass

    def soft_delete_note(self, note_id: str) -> None:
        """Soft-delete a note. Subclasses should override; default falls back to hard delete."""
        self.delete_note_by_id(note_id)

    @abstractmethod
    def save_character(self, character: Character) -> None:
        pass

    @abstractmethod
    def get_character_by_id(self, character_id: str) -> Optional[Character]:
        pass

    @abstractmethod
    def delete_character_by_id(self, character_id: str) -> None:
        pass

    @abstractmethod
    def save_map(self, map_obj: Map) -> None:
        pass

    @abstractmethod
    def get_map_by_id(self, map_id: str) -> Optional[Map]:
        pass

    @abstractmethod
    def delete_map_by_id(self, map_id: str) -> None:
        pass

    @abstractmethod
    def save_image(self, image: Image) -> None:
        pass

    @abstractmethod
    def get_image_by_id(self, image_id: str) -> Optional[Image]:
        pass

    @abstractmethod
    def delete_image_by_id(self, image_id: str) -> None:
        pass

    @abstractmethod
    def save_sound(self, sound: Sound) -> None:
        pass

    @abstractmethod
    def get_sound_by_id(self, sound_id: str) -> Optional[Sound]:
        pass

    @abstractmethod
    def delete_sound_by_id(self, sound_id: str) -> None:
        pass

    @abstractmethod
    def save_session(self, session: Session) -> None:
        pass

    @abstractmethod
    def get_session_by_id(self, session_id: str) -> Optional[Session]:
        pass

    @abstractmethod
    def delete_session_by_id(self, session_id: str) -> None:
        pass

    @abstractmethod
    def list_active_sessions(self) -> List[Session]:
        """Return all sessions that are active and not yet expired."""
        pass

    # --- Invite Codes ---
    @abstractmethod
    def save_invite(self, invite: InviteCode) -> None:
        pass

    @abstractmethod
    def get_invite_by_code(self, code: str) -> Optional[InviteCode]:
        pass

    @abstractmethod
    def get_invite_by_id(self, invite_id: str) -> Optional[InviteCode]:
        pass

    @abstractmethod
    def list_invites(self) -> List[InviteCode]:
        """Return all invite codes, newest first."""
        pass

    # --- PATH HELPERS ---
    @abstractmethod
    def absolute_path(self, rel: str) -> str:
        """
        Resolve a vault-relative path to an absolute filesystem path string.

        Use this instead of accessing ``storage.vault_path`` directly so that
        controllers remain backend-agnostic.
        """
        pass

    # --- GENERIC FILE & FOLDER HELPERS ---
    @abstractmethod
    def list_folders(self, parent: str = "") -> List[str]:
        pass

    @abstractmethod
    def list_notes(self, folder: str = "") -> List[str]:
        pass

    @abstractmethod
    def create_folder(self, path: str) -> None:
        pass

    @abstractmethod
    def delete_folder(self, path: str) -> None:
        pass

    @abstractmethod
    def move_folder(self, src_path: str, dest_path: str) -> None:
        pass

    @abstractmethod
    def folder_exists(self, path: str) -> bool:
        pass

    @abstractmethod
    def read_note(self, path: str) -> str:
        pass

    @abstractmethod
    def write_note(self, path: str, content: str) -> None:
        pass

    @abstractmethod
    def delete_note(self, path: str) -> None:
        pass

    @abstractmethod
    def note_exists(self, path: str) -> bool:
        pass

    @abstractmethod
    def move_note(self, src_path: str, dest_path: str) -> None:
        pass

    @abstractmethod
    def copy_note(self, src_path: str, dest_path: str) -> None:
        pass

    @abstractmethod
    def get_note_metadata(self, path: str) -> dict:
        pass

    @abstractmethod
    def get_folder_metadata(self, path: str) -> dict:
        pass

    # --- FAVORITES/STARS ---
    @abstractmethod
    def read_starred(self) -> Set[str]:
        pass

    @abstractmethod
    def write_starred(self, stars: Set[str]) -> None:
        pass

    # --- VERSIONING/BACKUPS ---
    @abstractmethod
    def backup_note(self, note_path: str) -> str:
        pass

    @abstractmethod
    def list_note_versions(self, note_path: str) -> List[str]:
        pass

    @abstractmethod
    def restore_note_version(self, note_path: str, version: str) -> None:
        pass

    # --- ATTACHMENTS ---
    @abstractmethod
    def list_attachments(self, folder: str = "") -> List[str]:
        pass

    @abstractmethod
    def add_attachment(self, folder: str, filename: str, data: bytes) -> None:
        pass

    @abstractmethod
    def delete_attachment(self, path: str) -> None:
        pass

    # --- SEARCH & EXISTENCE ---
    @abstractmethod
    def exists(self, rel_path: str) -> bool:
        """Return True if a note or folder at rel_path exists in the vault."""
        pass

    @abstractmethod
    def search_notes(self, query: str, vault_id: str = "", top_k: int = 100) -> List[Note]:
        """
        Full-text search across all notes in the vault.
        Returns up to top_k Note objects whose content or title matches query.
        vault_id filters to a specific vault when provided (multiuser use).
        """
        pass

    @abstractmethod
    def update_note_metadata(self, note_id: str, meta: dict) -> None:
        """
        Merge meta dict into the stored metadata for note_id.
        Only updates provided keys — does not overwrite the full record.
        """
        pass

    # --- Relationships ---

    @abstractmethod
    def create_relationship(self, rel: Relationship) -> Relationship:
        pass

    @abstractmethod
    def get_relationship(self, rel_id: str) -> Optional[Relationship]:
        pass

    @abstractmethod
    def list_relationships_for_entity(self, entity_id: str, vault_id: str) -> List[Relationship]:
        """Return all active relationships where source_id OR target_id == entity_id."""
        pass

    @abstractmethod
    def list_relationships(self, vault_id: str) -> List[Relationship]:
        """Return all active relationships for a vault."""
        pass

    @abstractmethod
    def relationship_exists(self, source_id: str, target_id: str, vault_id: str, rel_type: str) -> bool:
        """Return True when an active relationship with the same edge already exists."""
        pass

    @abstractmethod
    def delete_relationship(self, rel_id: str) -> bool:
        """Soft-delete a relationship (is_active=0). Returns True if found."""
        pass

    @abstractmethod
    def update_relationship(self, rel_id: str, updates: dict) -> Optional[Relationship]:
        """Apply updates dict to a relationship and return the updated record."""
        pass

    def search(self, query: "SearchQuery") -> "List[SearchResult]":
        """
        Structured search returning SearchResult objects.

        Default implementation wraps search_notes(); backends may override
        for performance (e.g. FTS index). Filters by query.search_type when
        the type is 'title' or 'tag'; falls back to full-text for 'keyword'.
        """
        from WorldStitch.search.search_types import SearchResult

        if query.search_type == "title":
            from pathlib import Path as _Path

            paths = [n for n in self.list_notes() if query.query_str.lower() in _Path(n).name.lower()]
            return [SearchResult(note_path=p, title=_Path(p).stem) for p in paths[: query.top_k]]

        if query.search_type == "tag":
            results = []
            for n in self.list_notes():
                try:
                    content = self.read_note(n)
                    tags = [
                        w.lstrip("#").strip("[]") for w in content.split() if w.startswith("#") or w.startswith("[[")
                    ]
                    if any(query.query_str.lower() in t.lower() for t in tags):
                        results.append(SearchResult(note_path=n, title=n))
                        if len(results) >= query.top_k:
                            break
                except Exception:
                    continue
            return results

        # "keyword" / default — full-text search via search_notes()
        notes = self.search_notes(query.query_str, vault_id=query.vault_id, top_k=query.top_k)
        return [
            SearchResult(
                note_path=n.id,
                title=n.title,
                snippet=(n.content or "")[:120],
            )
            for n in notes
        ]
