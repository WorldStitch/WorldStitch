"""
SQLite Storage Backend for MythosEngine.

A fully normalized SQLite implementation using SQLAlchemy 2.0 with declarative
ORM. All Pydantic models are stored as JSON blobs to avoid schema coupling.

The backend operates in "hybrid" mode:
  - Structured model data (User, Character, Note metadata) is stored in SQLite.
  - Note content is stored as markdown files in vault_path (delegated to pathlib).
  - Attachments, versions, and search indices are also file-based.

This approach provides ACID semantics for models while maintaining filesystem
flexibility for content. It scales better than pure file-storage but doesn't
require per-model schema migrations.

Thread-safe for multi-threaded PyQt6 applications via create_engine with
check_same_thread=False.
"""

import io
import json
import logging
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, create_engine, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from MythosEngine.core.event_bus import get_event_bus

# Mapped is in sqlalchemy.orm, not sqlalchemy.types
from MythosEngine.models.character import Character
from MythosEngine.models.folder import Folder
from MythosEngine.models.group import Group
from MythosEngine.models.image import Image
from MythosEngine.models.invite_code import InviteCode
from MythosEngine.models.map import Map
from MythosEngine.models.note import Note
from MythosEngine.models.session import Session as SessionModel
from MythosEngine.models.sound import Sound
from MythosEngine.models.user import User
from MythosEngine.models.vault import Vault
from MythosEngine.search.vector_index import VectorIndexConfig, VectorIndexLocation, VectorIndexManager
from MythosEngine.storage.storage_base import StorageBackend
from MythosEngine.sync.conflict_resolver import DEFAULT_CONFLICT_STRATEGY, ConflictRecord, ConflictResolver

# ============================================================================
# SQLAlchemy ORM Models
# ============================================================================


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    pass


class UserRecord(Base):
    """ORM model for User data — stored as JSON blob."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob
    analytics_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    system_role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", server_default="user")


class GroupRecord(Base):
    """ORM model for Group data — stored as JSON blob."""

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class VaultRecord(Base):
    """ORM model for Vault data — stored as JSON blob."""

    __tablename__ = "vaults"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    members_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class FolderRecord(Base):
    """ORM model for Folder data — stored as JSON blob."""

    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class NoteRecord(Base):
    """ORM model for Note metadata — content stored as file."""

    __tablename__ = "notes"
    __table_args__ = (
        Index("ix_notes_created_at", "created_at"),
        Index("ix_notes_owner_id", "owner_id"),
        Index("ix_notes_vault_id", "vault_id"),
        Index("ix_notes_is_deleted", "is_deleted"),
        Index("ix_notes_folder", "folder"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob (metadata only)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    folder: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, default="")
    # Denormalized columns for FTS5 triggers — populated in save_note()
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class CharacterRecord(Base):
    """ORM model for Character data — stored as JSON blob."""

    __tablename__ = "characters"
    __table_args__ = (Index("ix_characters_vault_id", "vault_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", server_default="")
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class MapRecord(Base):
    """ORM model for Map data — stored as JSON blob."""

    __tablename__ = "maps"
    __table_args__ = (Index("ix_maps_vault_id", "vault_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", server_default="")
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class ImageRecord(Base):
    """ORM model for Image data — stored as JSON blob."""

    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class SoundRecord(Base):
    """ORM model for Sound data — stored as JSON blob."""

    __tablename__ = "sounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class SessionRecord(Base):
    """ORM model for Session data — stored as JSON blob."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class SessionLogRecord(Base):
    """ORM model for D&D session log — normalized columns for queryability."""

    __tablename__ = "session_logs"
    __table_args__ = (Index("ix_session_logs_vault_id", "vault_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    session_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    raw_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    ai_recap: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    participants: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True, default="")
    xp_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    loot_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, onupdate=datetime.utcnow)
    owner_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, default="")


class StarredRecord(Base):
    """Store starred/favorite note IDs (one JSON blob with the entire set)."""

    __tablename__ = "starred"

    id: Mapped[str] = mapped_column(String(1), primary_key=True, default="1")
    data: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array


class InviteRecord(Base):
    """ORM model for InviteCode — stored as JSON blob."""

    __tablename__ = "invite_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class RelationshipRecord(Base):
    """Tracks [[wikilink]] relationships between notes (source → target)."""

    __tablename__ = "note_relationships"

    source_path: Mapped[str] = mapped_column(String(1024), primary_key=True)
    target_path: Mapped[str] = mapped_column(String(1024), primary_key=True)


class AnalyticsEventRecord(Base):
    """One row per analytics event — stored with JSON event_data payload."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_user_id", "user_id"),
        Index("ix_analytics_events_event_type", "event_type"),
        Index("ix_analytics_events_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


def _session_log_to_dict(record: SessionLogRecord) -> dict:
    """Convert a SessionLogRecord ORM row to a plain dict."""
    return {
        "id": record.id,
        "vault_id": record.vault_id or "",
        "title": record.title or "",
        "session_date": record.session_date or "",
        "summary": record.summary or "",
        "raw_notes": record.raw_notes or "",
        "ai_recap": record.ai_recap or "",
        "participants": record.participants or "",
        "xp_gained": record.xp_gained or 0,
        "loot_notes": record.loot_notes or "",
        "is_deleted": bool(record.is_deleted),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "owner_id": record.owner_id or "",
    }


# ============================================================================
# SQLiteBackend
# ============================================================================


class SQLiteBackend(StorageBackend):
    """
    SQLAlchemy-based SQLite backend for MythosEngine.

    All Pydantic models are serialized to JSON and stored as TEXT columns,
    avoiding schema coupling and making future migrations trivial.

    File-system operations (note content, attachments, versions) are delegated
    to pathlib in vault_path, following the same pattern as HybridStorage.

    Parameters
    ----------
    db_path : str
        Path to SQLite database file (e.g., "mythos_engine.db").
        Created automatically if it doesn't exist.
    vault_path : str, optional
        Root directory for markdown notes, attachments, and versions.
        If not provided, defaults to a `.vault` subdirectory next to the DB.
    """

    def __init__(self, db_path: str, vault_path: Optional[str] = None):
        """Initialize SQLite backend and create tables if needed."""
        self.db_path = Path(db_path)
        self.vault_path: Path = Path(vault_path or self.db_path.parent / ".vault").resolve()
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Create engine with check_same_thread=False for PyQt6 thread safety
        db_url = f"sqlite:///{self.db_path}"
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})

        # Create all tables on first run
        Base.metadata.create_all(self.engine)

        # Apply any pending Alembic migrations (stamps fresh DBs to head)
        try:
            from migrations.runner import run_migrations

            run_migrations(self.engine)
        except Exception:
            pass

        # FTS5 full-text search index
        self._fts_available = False
        raw_conn = self.engine.raw_connection()
        try:
            self._setup_fts(raw_conn)
            self._setup_campaign_columns(raw_conn)
            raw_conn.commit()
            self._fts_available = True
        except Exception as exc:
            logger.warning("FTS5 not available: %s — falling back to LIKE search.", exc)
        finally:
            raw_conn.close()

        # Add missing analytics columns for databases created before this feature.
        raw_conn = self.engine.raw_connection()
        try:
            self._setup_analytics(raw_conn)
            raw_conn.commit()
        except Exception:
            pass
        finally:
            raw_conn.close()

        # AI cost tracking — records token usage per user/vault/operation.
        from MythosEngine.ai.cost_tracker import CostTracker

        self.cost_tracker = CostTracker(self.engine)

        # Per-user OpenAI API key storage and monthly quota enforcement.
        from MythosEngine.ai.user_api_keys import UserApiKeyStore

        self.user_api_keys = UserApiKeyStore(self.engine)

        # Vector index — in-memory semantic search; builds lazily on first write.
        self.vector_index = VectorIndexManager(VectorIndexConfig(location=VectorIndexLocation.IN_MEMORY, enabled=True))

    def _session(self) -> Session:
        """Get a new database session."""
        return Session(self.engine)

    def _setup_fts(self, conn) -> None:
        """Create the FTS5 virtual table and sync triggers on the raw SQLite connection."""
        # Add missing notes columns for legacy databases.
        # This makes startup resilient when an older DB predates Alembic or
        # when migration stamping skipped table-alter migrations.
        for statement in (
            "ALTER TABLE notes ADD COLUMN created_at DATETIME",
            "ALTER TABLE notes ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE notes ADD COLUMN folder TEXT DEFAULT ''",
            "ALTER TABLE notes ADD COLUMN title TEXT DEFAULT ''",
            "ALTER TABLE notes ADD COLUMN content TEXT DEFAULT ''",
            "ALTER TABLE notes ADD COLUMN tags TEXT DEFAULT ''",
        ):
            try:
                conn.execute(statement)
            except Exception:
                pass  # column already exists

        for statement in (
            "ALTER TABLE characters ADD COLUMN vault_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE maps ADD COLUMN vault_id TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(statement)
            except Exception:
                pass  # column already exists

        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
            USING fts5(id UNINDEXED, title, content, tags, tokenize='porter ascii')
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
                INSERT INTO notes_fts(id, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE ON notes BEGIN
                UPDATE notes_fts SET title=new.title, content=new.content, tags=new.tags
                WHERE id=new.id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
                DELETE FROM notes_fts WHERE id=old.id;
            END
        """)

    def _setup_analytics(self, conn) -> None:
        """Add analytics_consent column to users table for legacy databases."""
        try:
            conn.execute("ALTER TABLE users ADD COLUMN analytics_consent INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists

    def _setup_campaign_columns(self, conn) -> None:
        """Add campaign_id column to characters, maps, and notes if not already present."""
        for statement in (
            "ALTER TABLE characters ADD COLUMN campaign_id TEXT",
            "ALTER TABLE maps ADD COLUMN campaign_id TEXT",
            "ALTER TABLE notes ADD COLUMN campaign_id TEXT",
        ):
            try:
                conn.execute(statement)
            except Exception:
                pass  # column already exists

    def _dnd_meta_path(self, subfolder: str, obj_id: str) -> Path:
        """Return the JSON path for a model object's metadata, creating dir if needed."""
        d = self.vault_path / ".dnd_meta" / subfolder
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{obj_id}.json"

    def _vault_dir_name(self, vault_id: str) -> str:
        if not vault_id:
            return "_default"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", vault_id)

    def _vault_root(self, vault_id: str = "") -> Path:
        if not vault_id:
            return self.vault_path
        root = self.vault_path / "_vaults" / self._vault_dir_name(vault_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _vault_abs(self, vault_id: str, rel: str) -> Path:
        return self._vault_root(vault_id) / rel

    def _permission_subject_ids(self) -> set[str]:
        subjects: set[str] = set()
        if self._current_user_id:
            subjects.add(self._current_user_id)
        if not self._current_user_id:
            return subjects
        try:
            with self._session() as session:
                record = session.query(UserRecord).filter(UserRecord.id == self._current_user_id).first()
                if record:
                    user = User.model_validate_json(record.data)
                    subjects.update(user.groups or [])
        except Exception:
            pass
        return subjects

    def _has_vault_access(self, vault_id: str) -> bool:
        if not vault_id:
            return True
        if self._is_admin or self._is_gm:
            return True
        with self._session() as session:
            record = session.query(VaultRecord).filter(VaultRecord.id == vault_id).first()
            if not record:
                return vault_id == "default"
            vault = Vault.model_validate_json(record.data)
            members = json.loads(record.members_json or "[]")
            subjects = self._permission_subject_ids()
            return bool(subjects.intersection(set(vault.permissions or {}))) or self._can_access(
                vault.owner_id,
                vault.permissions,
                members,
            )

    def _abs(self, rel: str) -> Path:
        """Resolve a relative vault path to an absolute Path."""
        return self.vault_path / rel

    def absolute_path(self, rel: str) -> str:
        """Public interface: resolve a vault-relative path to an absolute string."""
        return str(self._abs(rel))

    def _get_all_notes_for_index(self) -> list:
        """Return all vault notes as dicts for vector index building."""
        notes = []
        for p in self.vault_path.rglob("*.md"):
            if p.name.startswith("."):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                rel = str(p.relative_to(self.vault_path))
                notes.append({"note_path": rel, "title": p.stem, "content": content})
            except Exception:
                continue
        return notes

    def list_groups(self) -> List[Group]:
        groups: List[Group] = []
        with self._session() as session:
            for rec in session.query(GroupRecord).all():
                try:
                    group = Group.model_validate_json(rec.data)
                    if not getattr(group, "is_active", True):
                        continue
                    if (
                        self._is_admin
                        or self._is_gm
                        or group.owner_id == self._current_user_id
                        or self._current_user_id in (group.members or [])
                    ):
                        groups.append(group)
                except Exception:
                    continue
        return groups

    def list_vaults(self) -> List[Vault]:
        vaults: List[Vault] = []
        with self._session() as session:
            for rec in session.query(VaultRecord).all():
                try:
                    vault = Vault.model_validate_json(rec.data)
                    members = json.loads(rec.members_json or "[]")
                    if not getattr(vault, "is_active", True):
                        continue
                    if self._can_access(vault.owner_id, vault.permissions, members):
                        vaults.append(vault)
                except Exception:
                    continue
        vaults.sort(key=lambda item: (item.owner_id != (self._current_user_id or ""), item.name.lower()))
        return vaults

    # ========================================================================
    # Users
    # ========================================================================

    def save_user(self, user: User) -> None:
        """Save or update a User record."""
        email = getattr(user, "email", "") or ""
        system_role = getattr(user, "system_role", "user") or "user"
        with self._session() as session:
            record = session.query(UserRecord).filter(UserRecord.id == user.id).first()
            if record:
                record.email = email
                record.system_role = system_role
                record.data = user.model_dump_json()
            else:
                record = UserRecord(id=user.id, email=email, system_role=system_role, data=user.model_dump_json())
                session.add(record)
            session.commit()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve a User by ID."""
        with self._session() as session:
            record = session.query(UserRecord).filter(UserRecord.id == user_id).first()
            if record:
                return User.model_validate_json(record.data)
        return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Retrieve a User by email address (uses indexed email column)."""
        with self._session() as session:
            record = session.query(UserRecord).filter(UserRecord.email == email).first()
            if record:
                return User.model_validate_json(record.data)
            # Fallback: scan JSON blobs for rows written before the email column existed
            for rec in session.query(UserRecord).filter(UserRecord.email.is_(None)).all():
                user = User.model_validate_json(rec.data)
                if user.email == email:
                    return user
        return None

    def delete_user_by_id(self, user_id: str) -> None:
        """Delete a User by ID."""
        with self._session() as session:
            session.query(UserRecord).filter(UserRecord.id == user_id).delete()
            session.commit()

    # ========================================================================
    # Groups
    # ========================================================================

    def save_group(self, group: Group) -> None:
        """Save or update a Group record."""
        with self._session() as session:
            record = session.query(GroupRecord).filter(GroupRecord.id == group.id).first()
            if record:
                record.owner_id = group.owner_id
                record.data = group.model_dump_json()
            else:
                record = GroupRecord(id=group.id, owner_id=group.owner_id, data=group.model_dump_json())
                session.add(record)
            session.commit()

    def get_group_by_id(self, group_id: str) -> Optional[Group]:
        """Retrieve a Group by ID."""
        with self._session() as session:
            record = session.query(GroupRecord).filter(GroupRecord.id == group_id).first()
            if record:
                return Group.model_validate_json(record.data)
        return None

    def delete_group_by_id(self, group_id: str) -> None:
        """Delete a Group by ID."""
        with self._session() as session:
            session.query(GroupRecord).filter(GroupRecord.id == group_id).delete()
            session.commit()

    # ========================================================================
    # Vaults
    # ========================================================================

    def save_vault(self, vault: Vault) -> None:
        """Save or update a Vault record."""
        with self._session() as session:
            record = session.query(VaultRecord).filter(VaultRecord.id == vault.id).first()
            if record:
                record.owner_id = vault.owner_id
                record.members_json = json.dumps(vault.members)
                record.data = vault.model_dump_json()
            else:
                record = VaultRecord(
                    id=vault.id,
                    owner_id=vault.owner_id,
                    members_json=json.dumps(vault.members),
                    data=vault.model_dump_json(),
                )
                session.add(record)
            session.commit()

    def get_vault_by_id(self, vault_id: str) -> Optional[Vault]:
        """Retrieve a Vault by ID — returns None if user lacks access."""
        with self._session() as session:
            record = session.query(VaultRecord).filter(VaultRecord.id == vault_id).first()
            if record:
                vault = Vault.model_validate_json(record.data)
                members = json.loads(record.members_json or "[]")
                if not self._can_access(vault.owner_id, vault.permissions, members):
                    return None
                return vault
        return None

    def delete_vault_by_id(self, vault_id: str) -> None:
        """Delete a Vault by ID."""
        with self._session() as session:
            session.query(VaultRecord).filter(VaultRecord.id == vault_id).delete()
            session.commit()

    # ========================================================================
    # Folders
    # ========================================================================

    def save_folder(self, folder: Folder) -> None:
        """Save or update a Folder record and create its directory."""
        if folder.path:
            self._vault_abs(folder.vault_id, folder.path).mkdir(parents=True, exist_ok=True)

        with self._session() as session:
            record = session.query(FolderRecord).filter(FolderRecord.id == folder.id).first()
            if record:
                record.data = folder.model_dump_json()
            else:
                record = FolderRecord(id=folder.id, data=folder.model_dump_json())
                session.add(record)
            session.commit()

    def get_folder_by_id(self, folder_id: str) -> Optional[Folder]:
        """Retrieve a Folder by ID."""
        with self._session() as session:
            record = session.query(FolderRecord).filter(FolderRecord.id == folder_id).first()
            if record:
                folder = Folder.model_validate_json(record.data)
                if folder.vault_id and not self._has_vault_access(folder.vault_id):
                    return None
                return folder
        return None

    def delete_folder_by_id(self, folder_id: str) -> None:
        """Delete a Folder by ID and remove its directory."""
        folder = self.get_folder_by_id(folder_id)
        abs_path = self._vault_abs(folder.vault_id, folder.path or folder_id) if folder else self._abs(folder_id)
        if abs_path.is_dir():
            shutil.rmtree(abs_path)

        with self._session() as session:
            session.query(FolderRecord).filter(FolderRecord.id == folder_id).delete()
            session.commit()

    def list_folders(self, parent: str = "", vault_id: str = "") -> List[str]:
        """List all folder paths under parent (directory-based enumeration)."""
        root = (
            self._vault_abs(vault_id, parent)
            if vault_id and parent
            else self._vault_root(vault_id)
            if vault_id
            else self._abs(parent)
            if parent
            else self.vault_path
        )
        if not root.is_dir():
            return []
        return [
            str(p.relative_to(root if parent else (self._vault_root(vault_id) if vault_id else self.vault_path)))
            for p in root.rglob("*")
            if p.is_dir() and not p.name.startswith(".")
        ]

    def create_folder(self, path: str) -> None:
        """Create a folder directory."""
        self._abs(path).mkdir(parents=True, exist_ok=True)

    def delete_folder(self, path: str) -> None:
        """Delete a folder directory."""
        abs_path = self._abs(path)
        if abs_path.is_dir():
            shutil.rmtree(abs_path)

    def folder_exists(self, path: str) -> bool:
        """Check if a folder directory exists."""
        return self._abs(path).is_dir()

    def move_folder(self, src_path: str, dest_path: str) -> None:
        """Move a folder from src to dest."""
        src = self._abs(src_path)
        dst = self._abs(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

    def get_folder_metadata(self, path: str) -> dict:
        """Get folder metadata (timestamps and path info)."""
        abs_path = self._abs(path)
        stat = abs_path.stat()
        return {
            "path": path,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    # ========================================================================
    # Notes
    # ========================================================================

    def save_note(self, note: Note) -> None:
        """Save or update a Note (metadata in DB, content as markdown file)."""
        # Write content to markdown file
        if hasattr(note, "path") and note.path:
            abs_path = self._abs(note.path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(note.content, encoding="utf-8")

        # Store metadata in database (sync denormalized columns for indexing)
        _created_at = getattr(note, "created_at", None)
        _is_deleted = getattr(note, "is_deleted", False)
        _folder = getattr(note, "folder_id", "") or ""
        _title = note.title or ""
        _content = getattr(note, "content", "") or ""
        _tags = " ".join(getattr(note, "tags", []) or [])
        with self._session() as session:
            record = session.query(NoteRecord).filter(NoteRecord.id == note.id).first()
            if record:
                record.owner_id = note.owner_id
                record.vault_id = note.vault_id
                record.data = note.model_dump_json()
                record.created_at = _created_at
                record.is_deleted = _is_deleted
                record.folder = _folder
                record.title = _title
                record.content = _content
                record.tags = _tags
            else:
                record = NoteRecord(
                    id=note.id,
                    owner_id=note.owner_id,
                    vault_id=note.vault_id,
                    data=note.model_dump_json(),
                    created_at=_created_at,
                    is_deleted=_is_deleted,
                    folder=_folder,
                    title=_title,
                    content=_content,
                    tags=_tags,
                )
                session.add(record)
            session.commit()

    def get_note_by_id(self, note_id: str) -> Optional[Note]:
        """Retrieve a Note by ID — returns None if user lacks access."""
        with self._session() as session:
            record = session.query(NoteRecord).filter(NoteRecord.id == note_id).first()
            if record:
                note = Note.model_validate_json(record.data)
                if note.vault_id and not self._has_vault_access(note.vault_id):
                    return None
                if not self._can_access(note.owner_id, note.permissions):
                    return None
                if not (self._is_admin or self._is_gm) and (getattr(note, "meta", {}) or {}).get("gm_only"):
                    return None
                # Load content from file if available
                if hasattr(note, "path") and note.path:
                    abs_path = self._vault_abs(getattr(note, "vault_id", ""), note.path)
                    if abs_path.is_file():
                        note.content = abs_path.read_text(encoding="utf-8")
                return note
        return None

    def delete_note_by_id(self, note_id: str) -> None:
        """Delete a Note by ID."""
        with self._session() as session:
            record = session.query(NoteRecord).filter(NoteRecord.id == note_id).first()
            if record:
                note = Note.model_validate_json(record.data)
                # Delete markdown file
                if hasattr(note, "path") and note.path:
                    abs_path = self._abs(note.path)
                    if abs_path.is_file():
                        abs_path.unlink()

        with self._session() as session:
            session.query(NoteRecord).filter(NoteRecord.id == note_id).delete()
            session.commit()
        self.vector_index.clear()
        self.vector_index.build_index(self._get_all_notes_for_index())

    def soft_delete_note(self, note_id: str) -> None:
        """Soft-delete a note by setting is_deleted=True in both JSON blob and column."""
        with self._session() as session:
            record = session.query(NoteRecord).filter(NoteRecord.id == note_id).first()
            if record:
                note = Note.model_validate_json(record.data)
                note.is_deleted = True
                note.last_modified = datetime.utcnow()
                record.data = note.model_dump_json()
                record.is_deleted = True  # keep the indexed column in sync
                session.commit()

    def list_all_notes(
        self,
        folder: str = "",
        tag: str = "",
        skip: int = 0,
        limit: int = 0,
        vault_id: str = "",  # deprecated alias for campaign_id
        campaign_id: Optional[str] = None,
    ) -> List[Note]:
        """List notes directly from the SQLite database (not file-system based).

        This is the authoritative listing method for notes created via the API.
        File-based notes (legacy .md files) are NOT returned here; use
        ``search_notes("")`` for those.

        vault_id is a deprecated alias for campaign_id and will be removed in a future release.
        """
        filter_id = campaign_id or vault_id or ""
        results: List[Note] = []
        with self._session() as session:
            q = session.query(NoteRecord).filter(NoteRecord.is_deleted != True)  # noqa: E712
            if filter_id:
                # Prefer campaign_id column; fall back to vault_id column for legacy rows
                q = q.filter(
                    or_(NoteRecord.campaign_id == filter_id, NoteRecord.vault_id == filter_id)
                )
            if folder:
                q = q.filter(NoteRecord.folder == folder)
            records = q.order_by(NoteRecord.created_at.desc()).all()
            for record in records:
                try:
                    note = Note.model_validate_json(record.data)
                    if filter_id:
                        note_cid = getattr(note, "campaign_id", "") or getattr(note, "vault_id", "")
                        if note_cid != filter_id:
                            continue
                    if getattr(note, "vault_id", "") and not self._has_vault_access(note.vault_id):
                        continue
                    if not self._can_access(note.owner_id, note.permissions or {}):
                        continue
                    if not (self._is_admin or self._is_gm) and (getattr(note, "meta", {}) or {}).get("gm_only"):
                        continue
                    if tag and tag.lower() not in [t.lower() for t in (note.tags or [])]:
                        continue
                    results.append(note)
                except Exception:
                    continue
        if limit > 0:
            return results[skip : skip + limit]
        return results

    def list_all_folders(self, vault_id: str = "") -> List[Folder]:
        """List all folders directly from the SQLite database."""
        results: List[Folder] = []
        with self._session() as session:
            for record in session.query(FolderRecord).all():
                try:
                    folder = Folder.model_validate_json(record.data)
                    if vault_id and getattr(folder, "vault_id", "") != vault_id:
                        continue
                    if getattr(folder, "vault_id", "") and not self._has_vault_access(folder.vault_id):
                        continue
                    results.append(folder)
                except Exception:
                    continue
        return results

    def list_notes(self, folder: str = "", skip: int = 0, limit: int = 0) -> List[str]:
        """List note file paths the current user can access.

        Admins see all notes. Regular users see notes they own
        or notes explicitly shared with them. Soft-deleted notes are excluded.
        """
        # Collect accessible note IDs from the DB, excluding soft-deleted
        accessible_ids: set[str] = set()
        with self._session() as session:
            base_q = session.query(NoteRecord).filter(NoteRecord.is_deleted.is_not(True))
            if self._is_admin or self._is_gm:
                records = base_q.all()
            else:
                uid = self._current_user_id or ""
                records = base_q.filter(NoteRecord.owner_id == uid).all()
            for rec in records:
                note_data = json.loads(rec.data or "{}")
                perms = note_data.get("permissions", {})
                if self._can_access(rec.owner_id, perms):
                    accessible_ids.add(rec.id)
        # Fall back to filesystem listing if no DB records (legacy/unregistered notes)
        root = self._abs(folder) if folder else self.vault_path
        if not root.is_dir():
            return []
        all_paths = [str(p.relative_to(self.vault_path)) for p in root.rglob("*.md") if p.is_file()]
        if self._is_admin or self._is_gm or not self._current_user_id:
            result = all_paths
        else:
            # Return only paths that have a DB record the user can access
            result = [p for p in all_paths if p in accessible_ids or p.replace("\\", "/") in accessible_ids]
        if limit > 0:
            result = result[skip : skip + limit]
        return result

    def read_note(self, path: str) -> str:
        """Read note content from markdown file."""
        return self._abs(path).read_text(encoding="utf-8")

    def write_note(self, path: str, content: str, updated_at: Optional[datetime] = None) -> None:
        """Write note content to markdown file, resolving sync conflicts when detected."""
        abs_path = self._abs(path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        # Conflict detection: if the file on disk is newer than the incoming version,
        # the caller is writing a stale copy — apply the configured resolution strategy.
        if abs_path.is_file() and updated_at is not None:
            existing_content = abs_path.read_text(encoding="utf-8")
            if existing_content != content:
                existing_mtime = datetime.fromtimestamp(abs_path.stat().st_mtime)
                if existing_mtime > updated_at:
                    record = ConflictRecord(
                        note_path=path,
                        local_version=existing_content,
                        remote_version=content,
                        local_updated_at=existing_mtime,
                        remote_updated_at=updated_at,
                    )
                    content = ConflictResolver().resolve(record, DEFAULT_CONFLICT_STRATEGY)

        abs_path.write_text(content, encoding="utf-8")
        self.vector_index.build_index(self._get_all_notes_for_index())
        with self._session() as session:
            self._sync_mentions(session, path, content)
            session.commit()
        try:
            get_event_bus().note_saved.emit(path)
        except Exception:
            pass

    def delete_note(self, path: str) -> None:
        """Delete a note markdown file and remove its relationship records."""
        abs_path = self._abs(path)
        if abs_path.is_file():
            abs_path.unlink()
        with self._session() as session:
            session.query(RelationshipRecord).filter(RelationshipRecord.source_path == path).delete()
            session.commit()
        self.vector_index.clear()
        self.vector_index.build_index(self._get_all_notes_for_index())
        try:
            get_event_bus().note_deleted.emit(path)
        except Exception:
            pass

    def note_exists(self, path: str) -> bool:
        """Check if a note file exists."""
        return self._abs(path).is_file()

    def move_note(self, src_path: str, dest_path: str) -> None:
        """Move a note from src to dest, updating relationship source paths."""
        src = self._abs(src_path)
        dst = self._abs(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        with self._session() as session:
            for rec in session.query(RelationshipRecord).filter(RelationshipRecord.source_path == src_path).all():
                rec.source_path = dest_path
            session.commit()
        try:
            get_event_bus().note_moved.emit(src_path, dest_path)
        except Exception:
            pass

    def copy_note(self, src_path: str, dest_path: str) -> None:
        """Copy a note from src to dest."""
        src = self._abs(src_path)
        dst = self._abs(dest_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))

    def get_note_metadata(self, path: str) -> dict:
        """Get note metadata (timestamps and path info)."""
        abs_path = self._abs(path)
        stat = abs_path.stat()
        return {
            "path": path,
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    # ========================================================================
    # Characters, Maps, Images, Sounds, Sessions
    # ========================================================================

    def save_character(self, character: Character) -> None:
        """Save or update a Character record."""
        vault_id = getattr(character, "vault_id", "") or ""
        campaign_id = getattr(character, "campaign_id", None) or vault_id or ""
        with self._session() as session:
            record = session.query(CharacterRecord).filter(CharacterRecord.id == character.id).first()
            if record:
                record.vault_id = vault_id or record.vault_id
                record.campaign_id = campaign_id or record.campaign_id
                record.data = character.model_dump_json()
            else:
                record = CharacterRecord(id=character.id, vault_id=vault_id, campaign_id=campaign_id, data=character.model_dump_json())
                session.add(record)
            session.commit()

    def get_character_by_id(self, character_id: str) -> Optional[Character]:
        """Retrieve a Character by ID."""
        with self._session() as session:
            record = session.query(CharacterRecord).filter(CharacterRecord.id == character_id).first()
            if record:
                return Character.model_validate_json(record.data)
        return None

    def delete_character_by_id(self, character_id: str) -> None:
        """Delete a Character by ID."""
        with self._session() as session:
            session.query(CharacterRecord).filter(CharacterRecord.id == character_id).delete()
            session.commit()

    def list_characters(
        self,
        vault_id: str = "",  # deprecated alias for campaign_id
        campaign_id: Optional[str] = None,
        char_type: Optional[str] = None,
    ) -> List[Character]:
        """List non-deleted characters, optionally filtered by campaign_id and char_type ('player'|'npc').

        vault_id is a deprecated alias for campaign_id and will be removed in a future release.
        """
        filter_id = campaign_id or vault_id or ""
        results: List[Character] = []
        with self._session() as session:
            q = session.query(CharacterRecord)
            if filter_id:
                q = q.filter(
                    or_(CharacterRecord.campaign_id == filter_id, CharacterRecord.vault_id == filter_id)
                )
            for rec in q.all():
                try:
                    char = Character.model_validate_json(rec.data)
                    if getattr(char, "is_deleted", False):
                        continue
                    if char_type == "npc" and not getattr(char, "is_npc", False):
                        continue
                    if char_type == "player" and getattr(char, "is_npc", False):
                        continue
                    results.append(char)
                except Exception:
                    continue
        return results

    def soft_delete_character(self, character_id: str) -> None:
        """Soft-delete a character by setting is_deleted=True in the JSON blob."""
        with self._session() as session:
            record = session.query(CharacterRecord).filter(CharacterRecord.id == character_id).first()
            if record:
                try:
                    char = Character.model_validate_json(record.data)
                    char.is_deleted = True
                    char.last_modified = datetime.utcnow()
                    record.data = char.model_dump_json()
                    session.commit()
                except Exception:
                    pass

    def save_map(self, map_obj: Map) -> None:
        """Save or update a Map record."""
        vault_id = getattr(map_obj, "vault_id", "") or ""
        campaign_id = getattr(map_obj, "campaign_id", None) or vault_id or ""
        with self._session() as session:
            record = session.query(MapRecord).filter(MapRecord.id == map_obj.id).first()
            if record:
                record.vault_id = vault_id or record.vault_id
                record.campaign_id = campaign_id or record.campaign_id
                record.data = map_obj.model_dump_json()
            else:
                record = MapRecord(id=map_obj.id, vault_id=vault_id, campaign_id=campaign_id, data=map_obj.model_dump_json())
                session.add(record)
            session.commit()

    def get_map_by_id(self, map_id: str) -> Optional[Map]:
        """Retrieve a Map by ID."""
        with self._session() as session:
            record = session.query(MapRecord).filter(MapRecord.id == map_id).first()
            if record:
                return Map.model_validate_json(record.data)
        return None

    def delete_map_by_id(self, map_id: str) -> None:
        """Delete a Map by ID."""
        with self._session() as session:
            session.query(MapRecord).filter(MapRecord.id == map_id).delete()
            session.commit()

    def list_maps(
        self,
        vault_id: str = "",  # deprecated alias for campaign_id
        campaign_id: Optional[str] = None,
        map_type: Optional[str] = None,
    ) -> List[Map]:
        """Return all non-deleted Maps, optionally filtered by campaign_id and map_type.

        vault_id is a deprecated alias for campaign_id and will be removed in a future release.
        """
        filter_id = campaign_id or vault_id or ""
        results: List[Map] = []
        with self._session() as session:
            q = session.query(MapRecord)
            if filter_id:
                q = q.filter(
                    or_(MapRecord.campaign_id == filter_id, MapRecord.vault_id == filter_id)
                )
            for record in q.all():
                try:
                    map_obj = Map.model_validate_json(record.data)
                    if map_obj.is_deleted:
                        continue
                    if map_type and map_obj.map_type != map_type:
                        continue
                    results.append(map_obj)
                except Exception:
                    continue
        return results

    def soft_delete_map(self, map_id: str) -> None:
        """Soft-delete a map by setting is_deleted=True in its JSON blob."""
        with self._session() as session:
            record = session.query(MapRecord).filter(MapRecord.id == map_id).first()
            if record:
                map_obj = Map.model_validate_json(record.data)
                map_obj.is_deleted = True
                map_obj.last_modified = datetime.utcnow()
                record.data = map_obj.model_dump_json()
                session.commit()

    def save_image(self, image: Image) -> None:
        """Save or update an Image record."""
        with self._session() as session:
            record = session.query(ImageRecord).filter(ImageRecord.id == image.id).first()
            if record:
                record.data = image.model_dump_json()
            else:
                record = ImageRecord(id=image.id, data=image.model_dump_json())
                session.add(record)
            session.commit()

    def get_image_by_id(self, image_id: str) -> Optional[Image]:
        """Retrieve an Image by ID."""
        with self._session() as session:
            record = session.query(ImageRecord).filter(ImageRecord.id == image_id).first()
            if record:
                return Image.model_validate_json(record.data)
        return None

    def delete_image_by_id(self, image_id: str) -> None:
        """Delete an Image by ID."""
        with self._session() as session:
            session.query(ImageRecord).filter(ImageRecord.id == image_id).delete()
            session.commit()

    def save_sound(self, sound: Sound) -> None:
        """Save or update a Sound record."""
        with self._session() as session:
            record = session.query(SoundRecord).filter(SoundRecord.id == sound.id).first()
            if record:
                record.data = sound.model_dump_json()
            else:
                record = SoundRecord(id=sound.id, data=sound.model_dump_json())
                session.add(record)
            session.commit()

    def get_sound_by_id(self, sound_id: str) -> Optional[Sound]:
        """Retrieve a Sound by ID."""
        with self._session() as session:
            record = session.query(SoundRecord).filter(SoundRecord.id == sound_id).first()
            if record:
                return Sound.model_validate_json(record.data)
        return None

    def delete_sound_by_id(self, sound_id: str) -> None:
        """Delete a Sound by ID."""
        with self._session() as session:
            session.query(SoundRecord).filter(SoundRecord.id == sound_id).delete()
            session.commit()

    def save_session(self, session_obj: SessionModel) -> None:
        """Save or update a Session record."""
        with self._session() as session:
            record = session.query(SessionRecord).filter(SessionRecord.id == session_obj.id).first()
            if record:
                record.data = session_obj.model_dump_json()
            else:
                record = SessionRecord(id=session_obj.id, data=session_obj.model_dump_json())
                session.add(record)
            session.commit()

    def get_session_by_id(self, session_id: str) -> Optional[SessionModel]:
        """Retrieve a Session by ID."""
        with self._session() as session:
            record = session.query(SessionRecord).filter(SessionRecord.id == session_id).first()
            if record:
                return SessionModel.model_validate_json(record.data)
        return None

    def delete_session_by_id(self, session_id: str) -> None:
        """Delete a Session by ID."""
        with self._session() as session:
            session.query(SessionRecord).filter(SessionRecord.id == session_id).delete()
            session.commit()

    # ========================================================================
    # Session Logs (D&D campaign session records)
    # ========================================================================

    def list_session_logs(self, vault_id: str, skip: int = 0, limit: int = 50) -> Tuple[List[dict], int]:
        """Return non-deleted session logs for a vault, sorted by session_date desc."""
        with self._session() as session:
            q = (
                session.query(SessionLogRecord)
                .filter(
                    SessionLogRecord.vault_id == vault_id,
                    SessionLogRecord.is_deleted == False,  # noqa: E712
                )
                .order_by(SessionLogRecord.session_date.desc())
            )
            total = q.count()
            records = q.offset(skip).limit(limit).all()
            items = [_session_log_to_dict(r) for r in records]
        return items, total

    def get_session_log(self, session_id: str) -> Optional[dict]:
        """Return a single session log by ID, or None if not found/deleted."""
        with self._session() as session:
            record = (
                session.query(SessionLogRecord)
                .filter(
                    SessionLogRecord.id == session_id,
                    SessionLogRecord.is_deleted == False,  # noqa: E712
                )
                .first()
            )
            if record:
                return _session_log_to_dict(record)
        return None

    def save_session_log(self, data: dict) -> str:
        """Create or partially-update a session log; returns the record's id."""
        session_id = data.get("id") or str(uuid.uuid4())
        now = datetime.utcnow()
        updatable = [
            "title",
            "session_date",
            "summary",
            "raw_notes",
            "ai_recap",
            "participants",
            "xp_gained",
            "loot_notes",
        ]
        with self._session() as session:
            record = session.query(SessionLogRecord).filter(SessionLogRecord.id == session_id).first()
            if record:
                for field in updatable:
                    if field in data:
                        setattr(record, field, data[field])
                record.updated_at = now
            else:
                record = SessionLogRecord(
                    id=session_id,
                    vault_id=data.get("vault_id", ""),
                    title=data.get("title", ""),
                    session_date=data.get("session_date", ""),
                    summary=data.get("summary", ""),
                    raw_notes=data.get("raw_notes", ""),
                    ai_recap=data.get("ai_recap", ""),
                    participants=data.get("participants", ""),
                    xp_gained=data.get("xp_gained", 0),
                    loot_notes=data.get("loot_notes", ""),
                    is_deleted=False,
                    created_at=now,
                    updated_at=now,
                    owner_id=data.get("owner_id", ""),
                )
                session.add(record)
            session.commit()
        return session_id

    def soft_delete_session_log(self, session_id: str) -> None:
        """Soft-delete a session log by setting is_deleted=True."""
        with self._session() as session:
            record = session.query(SessionLogRecord).filter(SessionLogRecord.id == session_id).first()
            if record:
                record.is_deleted = True
                record.updated_at = datetime.utcnow()
                session.commit()

    # ========================================================================
    # Starred/Favorites
    # ========================================================================

    def read_starred(self) -> Set[str]:
        """Read the set of starred note IDs."""
        with self._session() as session:
            record = session.query(StarredRecord).filter(StarredRecord.id == "1").first()
            if record:
                try:
                    return set(json.loads(record.data))
                except (json.JSONDecodeError, TypeError):
                    return set()
        return set()

    def write_starred(self, stars: Set[str]) -> None:
        """Write the set of starred note IDs."""
        with self._session() as session:
            record = session.query(StarredRecord).filter(StarredRecord.id == "1").first()
            if record:
                record.data = json.dumps(list(stars))
            else:
                record = StarredRecord(id="1", data=json.dumps(list(stars)))
                session.add(record)
            session.commit()

    # ========================================================================
    # Versioning / Backups
    # ========================================================================

    def backup_note(self, note_path: str) -> str:
        """Create a timestamped backup of a note file."""
        vault_id = ""
        note = self.get_note_by_id(note_path)
        if note:
            vault_id = getattr(note, "vault_id", "")
        orig = self._vault_abs(vault_id, note_path) if vault_id else self._abs(note_path)
        version_root = self._vault_root(vault_id) if vault_id else self.vault_path
        version_dir = version_root / ".versions" / Path(note_path).parent
        version_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = version_dir / f"{orig.name}.{timestamp}.bak"
        shutil.copy2(str(orig), str(backup))
        return str(backup)

    def list_note_versions(self, note_path: str) -> List[str]:
        """List all backup versions of a note."""
        note = self.get_note_by_id(note_path)
        vault_id = getattr(note, "vault_id", "") if note else ""
        version_root = self._vault_root(vault_id) if vault_id else self.vault_path
        version_dir = version_root / ".versions" / Path(note_path).parent
        if not version_dir.is_dir():
            return []
        stem = Path(note_path).stem
        return [p.name for p in version_dir.iterdir() if p.name.startswith(stem) and p.suffix == ".bak"]

    def restore_note_version(self, note_path: str, version: str) -> None:
        """Restore a note from a backup version."""
        note = self.get_note_by_id(note_path)
        vault_id = getattr(note, "vault_id", "") if note else ""
        version_root = self._vault_root(vault_id) if vault_id else self.vault_path
        version_dir = version_root / ".versions" / Path(note_path).parent
        dest = self._vault_abs(vault_id, note_path) if vault_id else self._abs(note_path)
        shutil.copy2(str(version_dir / version), str(dest))

    # ========================================================================
    # Attachments
    # ========================================================================

    def list_attachments(self, folder: str = "", vault_id: str = "") -> List[str]:
        """List all attachments in a folder."""
        path = self._vault_root(vault_id) / "_attachments" / folder
        if not path.is_dir():
            return []
        return [p.name for p in path.iterdir() if p.is_file() and p.suffix != ".md"]

    def add_attachment(self, folder: str, filename: str, data: bytes, vault_id: str = "") -> None:
        """Add an attachment (binary data) to a folder."""
        dest = self._vault_root(vault_id) / "_attachments" / folder / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def delete_attachment(self, path: str, vault_id: str = "") -> None:
        """Delete an attachment."""
        abs_path = self._vault_root(vault_id) / "_attachments" / path
        if abs_path.is_file():
            abs_path.unlink()

    def export_vault_zip(self, vault_id: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            vault = self.get_vault_by_id(vault_id)
            if not vault:
                raise ValueError("Vault not found")
            zf.writestr("vault.json", vault.model_dump_json(indent=2))
            notes = self.list_all_notes(vault_id=vault_id)
            folders = self.list_all_folders(vault_id=vault_id)
            zf.writestr(
                "metadata/notes.json",
                json.dumps([note.model_dump(mode="json") for note in notes], indent=2, default=str),
            )
            zf.writestr(
                "metadata/folders.json",
                json.dumps([folder.model_dump(mode="json") for folder in folders], indent=2, default=str),
            )
            root = self._vault_root(vault_id)
            if root.exists():
                for path in root.rglob("*"):
                    if path.is_file():
                        zf.write(path, f"files/{path.relative_to(root)}")
        return buffer.getvalue()

    def import_vault_zip(
        self,
        payload: bytes,
        owner_id: str,
        name: Optional[str] = None,
        new_vault_id: Optional[str] = None,
    ) -> Vault:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
            vault_data = json.loads(zf.read("vault.json").decode("utf-8"))
            imported_vault = Vault.model_validate(vault_data)
            imported_vault.id = new_vault_id or str(uuid.uuid4())
            imported_vault.owner_id = owner_id
            imported_vault.name = name or f"{imported_vault.name} (Imported)"
            # Imported vault sharing is intentionally cleared so the receiving
            # environment never inherits stale access from the source system.
            imported_vault.members = []
            imported_vault.permissions = {}
            imported_vault.is_active = True
            self.save_vault(imported_vault)

            files_root = self._vault_root(imported_vault.id)
            for member in zf.namelist():
                if member.startswith("files/") and not member.endswith("/"):
                    rel = member.removeprefix("files/")
                    dest = files_root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(member))

            for entry in json.loads(zf.read("metadata/folders.json").decode("utf-8")):
                folder = Folder.model_validate(entry)
                folder.owner_id = owner_id
                folder.vault_id = imported_vault.id
                self.save_folder(folder)

            for entry in json.loads(zf.read("metadata/notes.json").decode("utf-8")):
                note = Note.model_validate(entry)
                note.owner_id = owner_id
                note.vault_id = imported_vault.id
                # Imported permissions and group bindings are intentionally reset so
                # the receiving vault never inherits stale access from another system.
                note.permissions = {}
                note.group_id = None
                self.save_note(note)

        return imported_vault

    def schedule_vault_backup(self, vault_id: str, cron: str) -> dict[str, Any]:
        settings_path = self._vault_root(vault_id) / ".backup_schedule.json"
        payload = {"vault_id": vault_id, "cron": cron, "updated_at": datetime.utcnow().isoformat()}
        settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    # ========================================================================
    # Search & Existence
    # ========================================================================

    def exists(self, rel_path: str) -> bool:
        """Check if a note or folder exists."""
        return self._abs(rel_path).exists()

    def search_notes_fts(
        self,
        query: str,
        vault_id: str = "",
        skip: int = 0,
        limit: int = 20,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        """FTS5-powered full-text search with BM25 ranking and snippet highlighting.

        Falls back to LIKE-based search when FTS5 is unavailable.
        Returns ``{items, total, skip, limit}``.
        """
        if not self._fts_available:
            return self._search_notes_like(query, vault_id, skip, limit, folder, tags, date_from, date_to)

        raw_conn = self.engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            sql = """
                SELECT
                    n.id,
                    n.data,
                    bm25(notes_fts) AS rank,
                    snippet(notes_fts, 2, '<mark>', '</mark>', '...', 20) AS snippet
                FROM notes_fts
                JOIN notes n ON notes_fts.id = n.id
                WHERE notes_fts MATCH ?
                  AND n.is_deleted = 0
            """
            params: list = [query]

            if vault_id:
                sql += " AND n.vault_id = ?"
                params.append(vault_id)
            if folder:
                sql += " AND (n.folder = ? OR n.folder LIKE ?)"
                params.extend([folder, f"{folder}/%"])
            if date_from:
                sql += " AND n.created_at >= ?"
                params.append(date_from)
            if date_to:
                sql += " AND n.created_at <= ?"
                params.append(date_to)

            sql += " ORDER BY rank"  # BM25 returns negatives; more negative = more relevant

            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except Exception as exc:
            logger.warning("FTS5 query failed (%s), falling back to LIKE search.", exc)
            raw_conn.close()
            return self._search_notes_like(query, vault_id, skip, limit, folder, tags, date_from, date_to)
        finally:
            raw_conn.close()

        all_items = []
        for row in rows:
            note_id, data_json, rank, snippet_text = row
            try:
                note = Note.model_validate_json(data_json)
            except Exception:
                continue

            # Filter by ALL required tags (post-SQL, since tags are stored in JSON)
            if tags:
                note_tags_lower = [t.lower() for t in (getattr(note, "tags", []) or [])]
                if not all(t.lower() in note_tags_lower for t in tags):
                    continue

            all_items.append(
                {
                    "id": note.id,
                    "title": note.title,
                    "folder_id": getattr(note, "folder_id", None),
                    "tags": getattr(note, "tags", []) or [],
                    "group_id": getattr(note, "group_id", None),
                    "owner_id": getattr(note, "owner_id", ""),
                    "is_deleted": getattr(note, "is_deleted", False),
                    "created_at": note.created_at,
                    "last_modified": note.last_modified,
                    "snippet": snippet_text or "",
                }
            )

        total = len(all_items)
        page = all_items[skip : skip + limit]
        return {"items": page, "total": total, "skip": skip, "limit": limit}

    def _search_notes_like(
        self,
        query: str,
        vault_id: str = "",
        skip: int = 0,
        limit: int = 20,
        folder: Optional[str] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        """LIKE-based search fallback used when FTS5 is unavailable."""
        notes_list = self.search_notes(query, vault_id=vault_id, top_k=10000)

        if folder:
            notes_list = [n for n in notes_list if (getattr(n, "folder_id", "") or "").startswith(folder)]
        if tags:
            for t in tags:
                notes_list = [n for n in notes_list if t.lower() in [x.lower() for x in (getattr(n, "tags", []) or [])]]
        if date_from:
            dt_from = datetime.fromisoformat(date_from)
            notes_list = [n for n in notes_list if n.created_at and n.created_at >= dt_from]
        if date_to:
            dt_to = datetime.fromisoformat(date_to)
            notes_list = [n for n in notes_list if n.created_at and n.created_at <= dt_to]

        total = len(notes_list)
        page = notes_list[skip : skip + limit]
        items = [
            {
                "id": n.id,
                "title": n.title,
                "folder_id": getattr(n, "folder_id", None),
                "tags": getattr(n, "tags", []) or [],
                "group_id": getattr(n, "group_id", None),
                "owner_id": getattr(n, "owner_id", ""),
                "is_deleted": getattr(n, "is_deleted", False),
                "created_at": n.created_at,
                "last_modified": n.last_modified,
                "snippet": "",
            }
            for n in page
        ]
        return {"items": items, "total": total, "skip": skip, "limit": limit}

    def search_notes(
        self,
        query: str,
        vault_id: str = "",
        top_k: int = 100,
        skip: int = 0,
        limit: int = 0,
        search_type: str = "fulltext",
    ) -> List[Note]:
        """
        Search across markdown notes.

        Case-insensitive substring match on title and content. Soft-deleted
        notes are excluded by cross-referencing the DB is_deleted column.
        When vault_id is provided, search is scoped to that vault's directory.
        """
        # Collect paths of soft-deleted notes from DB
        deleted_paths: set[str] = set()
        try:
            with self._session() as session:
                for rec in session.query(NoteRecord).filter(NoteRecord.is_deleted.is_(True)).all():
                    note_data = json.loads(rec.data or "{}")
                    path = note_data.get("path", "")
                    if path:
                        deleted_paths.add(path)
                        deleted_paths.add(path.replace("\\", "/"))
        except Exception:
            pass

        if search_type == "semantic" and self.vector_index.is_available():
            note_paths = self.vector_index.search(query, top_k=top_k)
            results: List[Note] = []
            for rel in note_paths:
                rel_fwd = rel.replace("\\", "/")
                if rel in deleted_paths or rel_fwd in deleted_paths:
                    continue
                p = self._vault_root(vault_id) / rel if vault_id else self.vault_path / rel
                if not p.is_file():
                    continue
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    results.append(
                        Note(
                            id=rel,
                            owner_id="system",
                            vault_id=vault_id or str(self.vault_path),
                            title=p.stem,
                            content=content,
                        )
                    )
                except Exception:
                    continue
            if limit > 0:
                return results[skip : skip + limit]
            return results

        # Fulltext: case-insensitive substring match on title and content.
        query_lower = query.lower()
        results: List[Note] = []
        search_root = self._vault_root(vault_id) if vault_id else self.vault_path
        for p in search_root.rglob("*.md"):
            if p.name.startswith("."):
                continue
            try:
                rel = str(p.relative_to(search_root))
                rel_fwd = rel.replace("\\", "/")
                if rel in deleted_paths or rel_fwd in deleted_paths:
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
                if query_lower in p.stem.lower() or query_lower in content.lower():
                    results.append(
                        Note(
                            id=rel,
                            owner_id="system",
                            vault_id=vault_id or str(search_root),
                            title=p.stem,
                            content=content,
                        )
                    )
                    if len(results) >= top_k:
                        break
            except Exception:
                continue

        if limit > 0:
            results = results[skip : skip + limit]
        return results

    def count_notes(self, folder: str = "", vault_id: str = "") -> int:
        """Return the count of non-deleted notes accessible to the current user."""
        with self._session() as session:
            q = session.query(NoteRecord).filter(NoteRecord.is_deleted.is_not(True))
            if vault_id:
                q = q.filter(NoteRecord.vault_id == vault_id)
            if not (self._is_admin or self._is_gm):
                uid = self._current_user_id or ""
                q = q.filter(NoteRecord.owner_id == uid)
            return q.count()

    def update_note_metadata(self, note_id: str, meta: dict) -> None:
        """
        Merge meta into the stored JSON metadata for note_id.
        Only updates the provided keys; non-overlapping keys are preserved.
        """
        with Session(self.engine) as session:
            record = session.scalar(select(NoteRecord).where(NoteRecord.id == note_id))
            if record:
                existing = {}
                try:
                    existing = json.loads(record.data) if record.data else {}
                except Exception:
                    pass
                existing.update(meta)
                record.data = json.dumps(existing)
                session.commit()

    # ========================================================================
    # Relationships / Wikilinks
    # ========================================================================

    def _sync_mentions(self, session: Session, source_path: str, content: str) -> None:
        """Replace all relationship rows for source_path with current [[wikilinks]]."""
        targets = set(re.findall(r"\[\[([^\[\]]+)\]\]", content))
        session.query(RelationshipRecord).filter(RelationshipRecord.source_path == source_path).delete()
        for target in targets:
            session.add(RelationshipRecord(source_path=source_path, target_path=target))

    def get_relationships(self, note_path: str) -> List[str]:
        """Return targets that note_path links to (forward links)."""
        with self._session() as session:
            rows = session.query(RelationshipRecord).filter(RelationshipRecord.source_path == note_path).all()
            return [r.target_path for r in rows]

    def get_backlinks(self, note_path: str) -> List[str]:
        """Return source paths of notes that link to note_path (back-links)."""
        with self._session() as session:
            rows = session.query(RelationshipRecord).filter(RelationshipRecord.target_path == note_path).all()
            return [r.source_path for r in rows]

    def upsert_relationship(self, source_path: str, target_path: str) -> None:
        """Insert a single source→target relationship if it doesn't exist."""
        with self._session() as session:
            existing = session.get(RelationshipRecord, (source_path, target_path))
            if not existing:
                session.add(RelationshipRecord(source_path=source_path, target_path=target_path))
                session.commit()

    # ========================================================================
    # Active Sessions (for admin panel)
    # ========================================================================

    def list_active_sessions(self) -> List[SessionModel]:
        """Return all sessions that are active and not yet expired."""
        results: List[SessionModel] = []
        with self._session() as session:
            for rec in session.query(SessionRecord).all():
                try:
                    s = SessionModel.model_validate_json(rec.data)
                    if s.is_active and not s.is_expired():
                        results.append(s)
                except Exception:
                    pass
        return results

    # ========================================================================
    # Invite Codes
    # ========================================================================

    def save_invite(self, invite: InviteCode) -> None:
        """Save or update an InviteCode record."""
        with self._session() as session:
            record = session.query(InviteRecord).filter(InviteRecord.id == invite.id).first()
            if record:
                record.code = invite.code.upper()
                record.data = invite.model_dump_json()
            else:
                record = InviteRecord(
                    id=invite.id,
                    code=invite.code.upper(),
                    data=invite.model_dump_json(),
                )
                session.add(record)
            session.commit()

    def get_invite_by_code(self, code: str) -> Optional[InviteCode]:
        """Look up an invite by its human-readable code (case-insensitive)."""
        with self._session() as session:
            record = session.query(InviteRecord).filter(InviteRecord.code == code.strip().upper()).first()
            if record:
                return InviteCode.model_validate_json(record.data)
        return None

    def get_invite_by_id(self, invite_id: str) -> Optional[InviteCode]:
        """Look up an invite by its UUID."""
        with self._session() as session:
            record = session.query(InviteRecord).filter(InviteRecord.id == invite_id).first()
            if record:
                return InviteCode.model_validate_json(record.data)
        return None

    def list_invites(self) -> List[InviteCode]:
        """Return all invite codes."""
        codes: List[InviteCode] = []
        with self._session() as session:
            for rec in session.query(InviteRecord).all():
                try:
                    codes.append(InviteCode.model_validate_json(rec.data))
                except Exception:
                    pass
        return codes

    # ========================================================================
    # Analytics
    # ========================================================================

    def save_analytics_event(self, user_id: str, event_type: str, event_data: Optional[dict] = None) -> None:
        """Persist an analytics event row."""
        record = AnalyticsEventRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            event_type=event_type,
            event_data=json.dumps(event_data or {}),
            created_at=datetime.utcnow(),
        )
        with self._session() as session:
            session.add(record)
            session.commit()

    def user_has_analytics_consent(self, user_id: str) -> bool:
        """Return True if the user has opted in to analytics."""
        with self._session() as session:
            record = session.query(UserRecord).filter(UserRecord.id == user_id).first()
            if record:
                return bool(getattr(record, "analytics_consent", False))
        return False

    def set_analytics_consent(self, user_id: str, consent: bool) -> None:
        """Set the user's analytics consent flag; creates a stub row if user is missing."""
        with self._session() as session:
            record = session.query(UserRecord).filter(UserRecord.id == user_id).first()
            if record:
                record.analytics_consent = consent
            else:
                record = UserRecord(id=user_id, email=None, data="{}", analytics_consent=consent)
                session.add(record)
            session.commit()

    def get_analytics_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
        days: int = 30,
    ) -> List[dict]:
        """Return analytics events filtered by user/type, ordered newest-first."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        with self._session() as session:
            q = session.query(AnalyticsEventRecord).filter(
                AnalyticsEventRecord.created_at >= cutoff
            )
            if user_id:
                q = q.filter(AnalyticsEventRecord.user_id == user_id)
            if event_type:
                q = q.filter(AnalyticsEventRecord.event_type == event_type)
            q = q.order_by(AnalyticsEventRecord.created_at.desc())
            if limit:
                q = q.limit(limit)
            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "event_type": r.event_type,
                    "event_data": json.loads(r.event_data or "{}"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in q.all()
            ]

    # Campaigns (new schema — tables created by migration 0005)
    # ========================================================================

    def _re_sub_slug(self, name: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "-", name.lower()).strip("-") or "campaign"

    def create_campaign(
        self,
        group_id: str,
        owner_user_id: str,
        name: str,
        description: str = "",
        system: str = "",
    ) -> dict:
        """Create a new campaign in the given group. Returns the campaign dict."""
        campaign_id = str(uuid.uuid4())
        slug = self._re_sub_slug(name)
        now = datetime.utcnow()
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                conn.execute(
                    _text(
                        "INSERT INTO campaigns "
                        "(id, group_id, name, slug, description, system, status, "
                        "created_by_user_id, created_at, updated_at) VALUES "
                        "(:id, :gid, :name, :slug, :desc, :sys, 'active', :uid, :now, :now)"
                    ),
                    dict(id=campaign_id, gid=group_id, name=name, slug=slug,
                         desc=description or "", sys=system or "", uid=owner_user_id, now=now),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("create_campaign failed: %s", exc)
        return self.get_campaign(campaign_id) or {"id": campaign_id, "group_id": group_id, "name": name}

    def _campaign_row_to_dict(self, row) -> dict:
        return {
            "id": row[0],
            "group_id": row[1],
            "name": row[2],
            "slug": row[3],
            "description": row[4] or "",
            "system": row[5] or "",
            "status": row[6] or "active",
            "created_by_user_id": row[7] or "",
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
            "deleted_at": row[10].isoformat() if row[10] else None,
        }

    def get_campaign(self, campaign_id: str) -> Optional[dict]:
        """Fetch a single campaign by ID; returns None if not found or deleted."""
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                row = conn.execute(
                    _text(
                        "SELECT id, group_id, name, slug, description, system, status, "
                        "created_by_user_id, created_at, updated_at, deleted_at "
                        "FROM campaigns WHERE id = :id AND deleted_at IS NULL"
                    ),
                    {"id": campaign_id},
                ).fetchone()
            if row:
                return self._campaign_row_to_dict(row)
        except Exception as exc:
            logger.warning("get_campaign failed: %s", exc)
        return None

    def list_campaigns_for_group(self, group_id: str) -> List[dict]:
        """Return all active campaigns for a group, ordered by name."""
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                rows = conn.execute(
                    _text(
                        "SELECT id, group_id, name, slug, description, system, status, "
                        "created_by_user_id, created_at, updated_at, deleted_at "
                        "FROM campaigns WHERE group_id = :gid AND deleted_at IS NULL "
                        "ORDER BY name"
                    ),
                    {"gid": group_id},
                ).fetchall()
            return [self._campaign_row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.warning("list_campaigns_for_group failed: %s", exc)
            return []

    def add_campaign_member(self, campaign_id: str, user_id: str, role: str = "player") -> dict:
        """Add or update a user's role in a campaign. Returns the membership dict."""
        member_id = str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                # Upsert: delete existing then insert (SQLite lacks ON CONFLICT UPDATE cleanly)
                conn.execute(
                    _text("DELETE FROM campaign_members WHERE campaign_id = :cid AND user_id = :uid"),
                    {"cid": campaign_id, "uid": user_id},
                )
                conn.execute(
                    _text(
                        "INSERT INTO campaign_members (id, campaign_id, user_id, role, joined_at, created_at) "
                        "VALUES (:id, :cid, :uid, :role, :now, :now)"
                    ),
                    {"id": member_id, "cid": campaign_id, "uid": user_id, "role": role, "now": now},
                )
                conn.commit()
        except Exception as exc:
            logger.warning("add_campaign_member failed: %s", exc)
        return {"campaign_id": campaign_id, "user_id": user_id, "role": role}

    def list_campaign_members(self, campaign_id: str) -> List[dict]:
        """Return all members of a campaign."""
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                rows = conn.execute(
                    _text(
                        "SELECT id, campaign_id, user_id, role, joined_at "
                        "FROM campaign_members WHERE campaign_id = :cid"
                    ),
                    {"cid": campaign_id},
                ).fetchall()
            return [
                {"id": r[0], "campaign_id": r[1], "user_id": r[2], "role": r[3],
                 "joined_at": r[4].isoformat() if r[4] else None}
                for r in rows
            ]
        except Exception as exc:
            logger.warning("list_campaign_members failed: %s", exc)
            return []

    # ========================================================================
    # Group Members (new schema — table created by migration 0005)
    # ========================================================================

    def add_group_member(self, group_id: str, user_id: str, role: str = "member") -> dict:
        """Add or update a user's role in a group via the group_members join table."""
        member_id = str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                conn.execute(
                    _text("DELETE FROM group_members WHERE group_id = :gid AND user_id = :uid"),
                    {"gid": group_id, "uid": user_id},
                )
                conn.execute(
                    _text(
                        "INSERT INTO group_members (id, group_id, user_id, role, joined_at) "
                        "VALUES (:id, :gid, :uid, :role, :now)"
                    ),
                    {"id": member_id, "gid": group_id, "uid": user_id, "role": role, "now": now},
                )
                conn.commit()
        except Exception as exc:
            logger.warning("add_group_member failed: %s", exc)
        return {"group_id": group_id, "user_id": user_id, "role": role}

    def list_group_members(self, group_id: str) -> List[dict]:
        """Return all members of a group from the group_members table."""
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                rows = conn.execute(
                    _text(
                        "SELECT id, group_id, user_id, role, joined_at "
                        "FROM group_members WHERE group_id = :gid"
                    ),
                    {"gid": group_id},
                ).fetchall()
            return [
                {"id": r[0], "group_id": r[1], "user_id": r[2], "role": r[3],
                 "joined_at": r[4].isoformat() if r[4] else None}
                for r in rows
            ]
        except Exception as exc:
            logger.warning("list_group_members failed: %s", exc)
            return []

    def list_groups_for_user(self, user_id: str) -> List[dict]:
        """Return all groups a user belongs to (via group_members table)."""
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                rows = conn.execute(
                    _text(
                        "SELECT gm.group_id, gm.role, gm.joined_at, "
                        "g.name, g.owner_id "
                        "FROM group_members gm "
                        "JOIN groups g ON g.id = gm.group_id "
                        "WHERE gm.user_id = :uid"
                    ),
                    {"uid": user_id},
                ).fetchall()
            return [
                {"group_id": r[0], "role": r[1],
                 "joined_at": r[2].isoformat() if r[2] else None,
                 "name": r[3], "owner_id": r[4]}
                for r in rows
            ]
        except Exception as exc:
            logger.warning("list_groups_for_user failed: %s", exc)
            return []

    # ========================================================================
    # Play Sessions (new schema — table created by migration 0005)
    # ========================================================================

    def _play_session_row_to_dict(self, row) -> dict:
        return {
            "id": row[0],
            "campaign_id": row[1],
            "created_by_user_id": row[2] or "",
            "title": row[3] or "",
            "session_number": row[4],
            "session_date": str(row[5]) if row[5] else None,
            "summary": row[6] or "",
            "raw_notes": row[7] or "",
            "ai_recap": row[8] or "",
            "xp_gained": row[9] or 0,
            "loot_notes": row[10] or "",
            "status": row[11] or "planned",
            "created_at": row[12].isoformat() if row[12] else None,
            "updated_at": row[13].isoformat() if row[13] else None,
        }

    def save_play_session(self, campaign_id: str, data: dict) -> str:
        """Create or update a play session. Returns the session ID."""
        session_id = data.get("id") or str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                existing = conn.execute(
                    _text("SELECT id FROM play_sessions WHERE id = :id"),
                    {"id": session_id},
                ).fetchone()
                if existing:
                    updatable = ["title", "session_number", "session_date", "summary",
                                 "raw_notes", "ai_recap", "xp_gained", "loot_notes", "status"]
                    sets = ", ".join(f"{f} = :{f}" for f in updatable if f in data)
                    if sets:
                        params = {f: data[f] for f in updatable if f in data}
                        params["id"] = session_id
                        params["now"] = now
                        conn.execute(_text(f"UPDATE play_sessions SET {sets}, updated_at = :now WHERE id = :id"), params)
                else:
                    conn.execute(
                        _text(
                            "INSERT INTO play_sessions "
                            "(id, campaign_id, created_by_user_id, title, session_number, "
                            "session_date, summary, raw_notes, ai_recap, xp_gained, loot_notes, "
                            "status, created_at, updated_at) VALUES "
                            "(:id, :cid, :uid, :title, :snum, :sdate, :summary, :raw_notes, "
                            ":ai_recap, :xp, :loot, :status, :now, :now)"
                        ),
                        {
                            "id": session_id, "cid": campaign_id,
                            "uid": data.get("created_by_user_id", ""),
                            "title": data.get("title", ""),
                            "snum": data.get("session_number"),
                            "sdate": data.get("session_date"),
                            "summary": data.get("summary", ""),
                            "raw_notes": data.get("raw_notes", ""),
                            "ai_recap": data.get("ai_recap", ""),
                            "xp": data.get("xp_gained", 0),
                            "loot": data.get("loot_notes", ""),
                            "status": data.get("status", "planned"),
                            "now": now,
                        },
                    )
                conn.commit()
        except Exception as exc:
            logger.warning("save_play_session failed: %s", exc)
        return session_id

    def get_play_session(self, session_id: str, campaign_id: Optional[str] = None) -> Optional[dict]:
        """Fetch a single play session; enforces campaign isolation if campaign_id is given."""
        try:
            from sqlalchemy import text as _text
            sql = (
                "SELECT id, campaign_id, created_by_user_id, title, session_number, "
                "session_date, summary, raw_notes, ai_recap, xp_gained, loot_notes, "
                "status, created_at, updated_at "
                "FROM play_sessions WHERE id = :id AND deleted_at IS NULL"
            )
            params: dict = {"id": session_id}
            if campaign_id:
                sql += " AND campaign_id = :cid"
                params["cid"] = campaign_id
            with self.engine.connect() as conn:
                row = conn.execute(_text(sql), params).fetchone()
            if row:
                return self._play_session_row_to_dict(row)
        except Exception as exc:
            logger.warning("get_play_session failed: %s", exc)
        return None

    def list_play_sessions(self, campaign_id: str, skip: int = 0, limit: int = 50) -> Tuple[List[dict], int]:
        """Return play sessions for a campaign, sorted newest first."""
        try:
            from sqlalchemy import text as _text
            with self.engine.connect() as conn:
                total_row = conn.execute(
                    _text("SELECT COUNT(*) FROM play_sessions WHERE campaign_id = :cid AND deleted_at IS NULL"),
                    {"cid": campaign_id},
                ).fetchone()
                total = total_row[0] if total_row else 0
                rows = conn.execute(
                    _text(
                        "SELECT id, campaign_id, created_by_user_id, title, session_number, "
                        "session_date, summary, raw_notes, ai_recap, xp_gained, loot_notes, "
                        "status, created_at, updated_at "
                        "FROM play_sessions WHERE campaign_id = :cid AND deleted_at IS NULL "
                        "ORDER BY session_date DESC, created_at DESC "
                        "LIMIT :lim OFFSET :off"
                    ),
                    {"cid": campaign_id, "lim": limit, "off": skip},
                ).fetchall()
            return [self._play_session_row_to_dict(r) for r in rows], total
        except Exception as exc:
            logger.warning("list_play_sessions failed: %s", exc)
            return [], 0

    def delete_play_session(self, session_id: str, campaign_id: Optional[str] = None) -> None:
        """Soft-delete a play session by setting deleted_at."""
        try:
            from sqlalchemy import text as _text
            now = datetime.utcnow()
            sql = "UPDATE play_sessions SET deleted_at = :now WHERE id = :id"
            params: dict = {"now": now, "id": session_id}
            if campaign_id:
                sql += " AND campaign_id = :cid"
                params["cid"] = campaign_id
            with self.engine.connect() as conn:
                conn.execute(_text(sql), params)
                conn.commit()
        except Exception as exc:
            logger.warning("delete_play_session failed: %s", exc)
