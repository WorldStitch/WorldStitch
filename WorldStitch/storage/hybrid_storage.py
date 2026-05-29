"""
HybridStorage — the primary storage backend for WorldStitch.

Notes and folders live as markdown files inside the vault directory.
All structured model data (characters, maps, etc.) is stored as JSON
in a hidden .ws_meta subfolder inside the vault.
Users and groups are stored in a global data directory (~/.worldstitch_ai/).

All path handling uses pathlib.Path for cross-platform compatibility.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

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
from WorldStitch.storage.storage_base import StorageBackend


class HybridStorage(StorageBackend):
    """
    Hybrid backend: notes/folders as markdown in vault,
    structured models as JSON in .ws_meta,
    users/groups in global storage.
    """

    def __init__(self, vault_path: str, global_data_path: str = "~/.worldstitch_ai/"):
        self.vault_path: Path = Path(vault_path).resolve()
        self.global_data_path: Path = Path(global_data_path).expanduser()
        self.global_data_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _meta_path(self, subfolder: str, obj_id: str) -> Path:
        """Return the JSON path for a model object, creating the dir if needed."""
        d = self.vault_path / ".ws_meta" / subfolder
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{obj_id}.json"

    def _meta_dir(self, subfolder: str) -> Path:
        """Return the directory for a model subfolder, creating it if needed."""
        d = self.vault_path / ".ws_meta" / subfolder
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _global_path(self, model: str) -> Path:
        return self.global_data_path / f"{model}s.json"

    def _load_global(self, model: str) -> Dict:
        path = self._global_path(model)
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_global(self, model: str, data: Dict) -> None:
        path = self._global_path(model)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _abs(self, rel: str) -> Path:
        """Resolve a relative vault path to an absolute Path."""
        return self.vault_path / rel

    def absolute_path(self, rel: str) -> str:
        """Public interface: resolve a vault-relative path to an absolute string."""
        return str(self._abs(rel))

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def save_user(self, user: User) -> None:
        users = self._load_global("user")
        users[user.id] = user.model_dump()
        self._save_global("user", users)

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        data = self._load_global("user").get(user_id)
        return User.model_validate(data) if data else None

    def get_user_by_email(self, email: str) -> Optional[User]:
        for data in self._load_global("user").values():
            if data.get("email") == email:
                return User.model_validate(data)
        return None

    def delete_user_by_id(self, user_id: str) -> None:
        users = self._load_global("user")
        if user_id in users:
            del users[user_id]
            self._save_global("user", users)

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def save_group(self, group: Group) -> None:
        groups = self._load_global("group")
        groups[group.id] = group.model_dump()
        self._save_global("group", groups)

    def get_group_by_id(self, group_id: str) -> Optional[Group]:
        data = self._load_global("group").get(group_id)
        return Group.model_validate(data) if data else None

    def delete_group_by_id(self, group_id: str) -> None:
        groups = self._load_global("group")
        if group_id in groups:
            del groups[group_id]
            self._save_global("group", groups)

    # ------------------------------------------------------------------
    # Vaults
    # ------------------------------------------------------------------

    def save_vault(self, vault: Vault) -> None:
        path = self._meta_path("vaults", vault.id)
        path.write_text(json.dumps(vault.model_dump(), indent=2), encoding="utf-8")

    def get_vault_by_id(self, vault_id: str) -> Optional[Vault]:
        path = self._meta_path("vaults", vault_id)
        if not path.is_file():
            return None
        return Vault.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def delete_vault_by_id(self, vault_id: str) -> None:
        path = self._meta_path("vaults", vault_id)
        if path.is_file():
            path.unlink()

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    def save_folder(self, folder: Folder) -> None:
        if folder.path:
            self._abs(folder.path).mkdir(parents=True, exist_ok=True)
        meta_path = self._meta_path("folders", folder.id)
        meta_path.write_text(json.dumps(folder.model_dump(), indent=2), encoding="utf-8")

    def get_folder_by_id(self, folder_id: str) -> Optional[Folder]:
        abs_path = self._abs(folder_id)
        meta_path = self._meta_path("folders", folder_id)
        if abs_path.is_dir() and meta_path.is_file():
            return Folder.model_validate(json.loads(meta_path.read_text(encoding="utf-8")))
        if abs_path.is_dir():
            return Folder(id=folder_id, owner_id="system", name=abs_path.name, path=folder_id)
        return None

    def delete_folder_by_id(self, folder_id: str) -> None:
        abs_path = self._abs(folder_id)
        if abs_path.is_dir():
            shutil.rmtree(abs_path)
        meta_path = self._meta_path("folders", folder_id)
        if meta_path.is_file():
            meta_path.unlink()

    def list_folders(self, parent: str = "") -> List[str]:
        root = self._abs(parent) if parent else self.vault_path
        return [
            str(p.relative_to(self.vault_path)) for p in root.rglob("*") if p.is_dir() and not p.name.startswith(".")
        ]

    def create_folder(self, path: str) -> None:
        self._abs(path).mkdir(parents=True, exist_ok=True)

    def delete_folder(self, path: str) -> None:
        abs_path = self._abs(path)
        if abs_path.is_dir():
            shutil.rmtree(abs_path)

    def folder_exists(self, path: str) -> bool:
        return self._abs(path).is_dir()

    def move_folder(self, src_path: str, dest_path: str) -> None:
        src = self._abs(src_path)
        dst = self._abs(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    def get_folder_metadata(self, path: str) -> Dict:
        abs_path = self._abs(path)
        stat = abs_path.stat()
        return {
            "path": path,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def save_note(self, note: Note) -> None:
        if hasattr(note, "path") and note.path:
            abs_path = self._abs(note.path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(note.content, encoding="utf-8")
        meta_path = self._meta_path("notes", note.id)
        meta_path.write_text(json.dumps(note.model_dump(), indent=2), encoding="utf-8")

    def get_note_by_id(self, note_id: str) -> Optional[Note]:
        abs_path = self._abs(note_id)
        meta_path = self._meta_path("notes", note_id)
        if not abs_path.is_file():
            return None
        if meta_path.is_file():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            data["content"] = self.read_note(note_id)
            return Note.model_validate(data)
        content = abs_path.read_text(encoding="utf-8")
        return Note(
            id=note_id,
            owner_id="system",
            vault_id="",
            title=abs_path.name,
            content=content,
        )

    def delete_note_by_id(self, note_id: str) -> None:
        abs_path = self._abs(note_id)
        if abs_path.is_file():
            abs_path.unlink()
        meta_path = self._meta_path("notes", note_id)
        if meta_path.is_file():
            meta_path.unlink()

    def list_notes(self, folder: str = "") -> List[str]:
        root = self._abs(folder) if folder else self.vault_path
        return [str(p.relative_to(self.vault_path)) for p in root.rglob("*.md") if p.is_file()]

    def read_note(self, path: str) -> str:
        return self._abs(path).read_text(encoding="utf-8")

    def write_note(self, path: str, content: str) -> None:
        abs_path = self._abs(path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")

    def delete_note(self, path: str) -> None:
        abs_path = self._abs(path)
        if abs_path.is_file():
            abs_path.unlink()

    def note_exists(self, path: str) -> bool:
        return self._abs(path).is_file()

    def move_note(self, src_path: str, dest_path: str) -> None:
        src = self._abs(src_path)
        dst = self._abs(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    def copy_note(self, src_path: str, dest_path: str) -> None:
        src = self._abs(src_path)
        dst = self._abs(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))

    def get_note_metadata(self, path: str) -> Dict:
        abs_path = self._abs(path)
        stat = abs_path.stat()
        return {
            "path": path,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    # ------------------------------------------------------------------
    # Characters, Maps, Images, Sounds, Sessions — JSON model storage
    # ------------------------------------------------------------------

    def save_character(self, character: Character) -> None:
        p = self._meta_path("characters", character.id)
        p.write_text(json.dumps(character.model_dump(), indent=2), encoding="utf-8")

    def get_character_by_id(self, character_id: str) -> Optional[Character]:
        p = self._meta_path("characters", character_id)
        return Character.model_validate(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None

    def delete_character_by_id(self, character_id: str) -> None:
        p = self._meta_path("characters", character_id)
        if p.is_file():
            p.unlink()

    def save_map(self, map_obj: Map) -> None:
        p = self._meta_path("maps", map_obj.id)
        p.write_text(json.dumps(map_obj.model_dump(), indent=2), encoding="utf-8")

    def get_map_by_id(self, map_id: str) -> Optional[Map]:
        p = self._meta_path("maps", map_id)
        return Map.model_validate(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None

    def delete_map_by_id(self, map_id: str) -> None:
        p = self._meta_path("maps", map_id)
        if p.is_file():
            p.unlink()

    def save_image(self, image: Image) -> None:
        p = self._meta_path("images", image.id)
        p.write_text(json.dumps(image.model_dump(), indent=2), encoding="utf-8")

    def get_image_by_id(self, image_id: str) -> Optional[Image]:
        p = self._meta_path("images", image_id)
        return Image.model_validate(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None

    def delete_image_by_id(self, image_id: str) -> None:
        p = self._meta_path("images", image_id)
        if p.is_file():
            p.unlink()

    def save_sound(self, sound: Sound) -> None:
        p = self._meta_path("sounds", sound.id)
        p.write_text(json.dumps(sound.model_dump(), indent=2), encoding="utf-8")

    def get_sound_by_id(self, sound_id: str) -> Optional[Sound]:
        p = self._meta_path("sounds", sound_id)
        return Sound.model_validate(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None

    def delete_sound_by_id(self, sound_id: str) -> None:
        p = self._meta_path("sounds", sound_id)
        if p.is_file():
            p.unlink()

    def save_session(self, session: Session) -> None:
        p = self._meta_path("sessions", session.id)
        p.write_text(json.dumps(session.model_dump(), indent=2), encoding="utf-8")

    def get_session_by_id(self, session_id: str) -> Optional[Session]:
        p = self._meta_path("sessions", session_id)
        return Session.model_validate(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None

    def delete_session_by_id(self, session_id: str) -> None:
        p = self._meta_path("sessions", session_id)
        if p.is_file():
            p.unlink()

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------

    def read_timeline(self) -> list:
        path = self.vault_path / ".ws_meta" / "timeline.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def save_timeline(self, events: list) -> None:
        meta_dir = self.vault_path / ".ws_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "timeline.json").write_text(json.dumps(events, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Stars / Favorites
    # ------------------------------------------------------------------

    def read_starred(self) -> Set[str]:
        star_path = self.vault_path / ".starred.json"
        if not star_path.exists():
            return set()
        return set(json.loads(star_path.read_text(encoding="utf-8")))

    def write_starred(self, stars: Set[str]) -> None:
        star_path = self.vault_path / ".starred.json"
        star_path.write_text(json.dumps(list(stars)), encoding="utf-8")

    # ------------------------------------------------------------------
    # Versioning / Backups
    # ------------------------------------------------------------------

    def backup_note(self, note_path: str) -> str:
        orig = self._abs(note_path)
        version_dir = self.vault_path / ".versions" / Path(note_path).parent
        version_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = version_dir / f"{orig.name}.{timestamp}.bak"
        shutil.copy2(str(orig), str(backup))
        return str(backup)

    def list_note_versions(self, note_path: str) -> List[str]:
        version_dir = self.vault_path / ".versions" / Path(note_path).parent
        if not version_dir.is_dir():
            return []
        stem = Path(note_path).stem
        return [p.name for p in version_dir.iterdir() if p.name.startswith(stem) and p.suffix == ".bak"]

    def restore_note_version(self, note_path: str, version: str) -> None:
        version_dir = self.vault_path / ".versions" / Path(note_path).parent
        shutil.copy2(str(version_dir / version), str(self._abs(note_path)))

    # ------------------------------------------------------------------
    # Attachments
    # ------------------------------------------------------------------

    def list_attachments(self, folder: str = "") -> List[str]:
        path = self.vault_path / "_attachments" / folder
        if not path.is_dir():
            return []
        return [p.name for p in path.iterdir() if p.is_file() and p.suffix != ".md"]

    def add_attachment(self, folder: str, filename: str, data: bytes) -> None:
        dest = self.vault_path / "_attachments" / folder / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def delete_attachment(self, path: str) -> None:
        abs_path = self.vault_path / "_attachments" / path
        if abs_path.is_file():
            abs_path.unlink()

    # ------------------------------------------------------------------
    # Search & Existence
    # ------------------------------------------------------------------

    def exists(self, rel_path: str) -> bool:
        """Return True if a note or folder at rel_path exists in the vault."""
        p = self._abs(rel_path)
        return p.exists()

    def search_notes(self, query: str, vault_id: str = "", top_k: int = 100) -> List[Note]:
        """
        Simple full-text search across all markdown notes in the vault.
        Case-insensitive substring match on title and content.
        vault_id is accepted for interface compatibility (multiuser) but
        HybridStorage is single-vault — all notes are in self.vault_path.
        """
        query_lower = query.lower()
        results: List[Note] = []
        for p in self.vault_path.rglob("*.md"):
            if p.name.startswith("."):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                if query_lower in p.stem.lower() or query_lower in content.lower():
                    rel = str(p.relative_to(self.vault_path))
                    results.append(
                        Note(
                            id=rel,
                            owner_id="system",
                            vault_id=vault_id or str(self.vault_path),
                            title=p.stem,
                            content=content,
                        )
                    )
                    if len(results) >= top_k:
                        break
            except Exception:
                continue
        return results

    def update_note_metadata(self, note_id: str, meta: dict) -> None:
        """
        Merge meta into the stored JSON metadata for note_id.
        Only updates the provided keys — non-overlapping keys are preserved.
        """
        meta_path = self._meta_path("notes", note_id)
        if meta_path.is_file():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            existing.update(meta)
            meta_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def create_relationship(self, rel: Relationship) -> Relationship:
        path = self._meta_path("relationships", rel.id)
        path.write_text(json.dumps(rel.model_dump(mode="json"), indent=2), encoding="utf-8")
        return rel

    def get_relationship(self, rel_id: str) -> Optional[Relationship]:
        path = self._meta_path("relationships", rel_id)
        if not path.is_file():
            return None
        return Relationship.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list_relationships_for_entity(self, entity_id: str, vault_id: str) -> List[Relationship]:
        return [
            rel for rel in self.list_relationships(vault_id) if rel.source_id == entity_id or rel.target_id == entity_id
        ]

    def list_relationships(self, vault_id: str) -> List[Relationship]:
        rel_dir = self._meta_dir("relationships")
        results: List[Relationship] = []
        for path in rel_dir.glob("*.json"):
            try:
                rel = Relationship.model_validate(json.loads(path.read_text(encoding="utf-8")))
                if not vault_id or rel.vault_id == vault_id:
                    results.append(rel)
            except Exception:
                continue
        return results

    def relationship_exists(self, source_id: str, target_id: str, vault_id: str, rel_type: str) -> bool:
        rel_dir = self._meta_dir("relationships")
        for path in rel_dir.glob("*.json"):
            try:
                rel = Relationship.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if vault_id and rel.vault_id != vault_id:
                continue
            if rel.source_id == source_id and rel.target_id == target_id and rel.relationship_type == rel_type:
                return True
        return False

    def delete_relationship(self, rel_id: str) -> bool:
        path = self._meta_path("relationships", rel_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def update_relationship(self, rel_id: str, updates: dict) -> Optional[Relationship]:
        rel = self.get_relationship(rel_id)
        if rel is None:
            return None
        updated = rel.model_copy(update=updates)
        self.create_relationship(updated)
        return updated

    # ------------------------------------------------------------------
    # Active Sessions
    # ------------------------------------------------------------------

    def list_active_sessions(self) -> List[Session]:
        """Return all sessions that are active and not yet expired."""
        session_dir = self._meta_dir("sessions")
        results: List[Session] = []
        for p in session_dir.glob("*.json"):
            try:
                s = Session.model_validate(json.loads(p.read_text(encoding="utf-8")))
                if s.is_active and not s.is_expired():
                    results.append(s)
            except Exception:
                continue
        return results

    # ------------------------------------------------------------------
    # Invite Codes
    # ------------------------------------------------------------------

    def save_invite(self, invite: "InviteCode") -> None:
        p = self._meta_path("invites", invite.id)
        p.write_text(json.dumps(invite.model_dump(), indent=2), encoding="utf-8")

    def get_invite_by_code(self, code: str) -> Optional["InviteCode"]:
        invite_dir = self._meta_dir("invites")
        # Invite codes are always stored and compared in uppercase (see save_invite / InviteManager).
        code_upper = code.strip().upper()
        for p in invite_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("code", "").upper() == code_upper:
                    return InviteCode.model_validate(data)
            except Exception:
                continue
        return None

    def get_invite_by_id(self, invite_id: str) -> Optional["InviteCode"]:
        p = self._meta_path("invites", invite_id)
        if not p.is_file():
            return None
        return InviteCode.model_validate(json.loads(p.read_text(encoding="utf-8")))

    def list_invites(self) -> List["InviteCode"]:
        """Return all invite codes."""
        invite_dir = self._meta_dir("invites")
        codes: List[InviteCode] = []
        for p in invite_dir.glob("*.json"):
            try:
                codes.append(InviteCode.model_validate(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return codes
