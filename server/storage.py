"""
Async storage service for WorldStitch — the single data-access layer for
the FastAPI server.

Replaces the legacy WorldStitch/storage (sync SQLAlchemy + psycopg2) and
WorldStitch/managers layers. Differences from the legacy design:

- Every method is async and runs on the shared asyncpg engine.
- Caller identity is passed per call as an ``Actor`` instead of being
  stored on the backend instance (``set_user_context``). The old design
  kept the active user as mutable instance state, which under async
  concurrency lets one request's identity leak into another's queries.
- Note content lives in the database only. The legacy markdown-file
  mirror was ephemeral on Railway and is gone.

Permission semantics are ported unchanged: admins see everything; owners
always have access; explicit permission entries and vault membership
grant access; default deny.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from server.orm import (
    AIConversationRecord,
    AIUsageRecord,
    AnalyticsEventRecord,
    CharacterRecord,
    EdgeRecord,
    FolderRecord,
    GroupRecord,
    ImageRecord,
    InviteRecord,
    MapRecord,
    NoteRecord,
    NoteRelationshipRecord,
    SessionLogRecord,
    SessionRecord,
    SoundRecord,
    StarredRecord,
    UserApiKeyRecord,
    UserRecord,
    VaultInviteRecord,
    VaultMemberRecord,
    VaultRecord,
)
from WorldStitch.models.character import Character
from WorldStitch.models.folder import Folder
from WorldStitch.models.group import Group
from WorldStitch.models.image import Image
from WorldStitch.models.invite_code import InviteCode
from WorldStitch.models.map import Map
from WorldStitch.models.note import Note
from WorldStitch.models.relationship import Relationship
from WorldStitch.models.session import Session as SessionModel
from WorldStitch.models.sound import Sound
from WorldStitch.models.user import User
from WorldStitch.models.vault import Vault
from WorldStitch.models.vault_invite import VaultInvite
from WorldStitch.utils.audit_logger import audit

logger = logging.getLogger(__name__)

# ── AI pricing (moved from WorldStitch/ai/cost_tracker.py) ────────────────────
# model_key -> (prompt_$/1M_tokens, completion_$/1M_tokens)
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.0, 15.0),
    "claude-3-5-sonnet": (3.0, 15.0),
}
_DEFAULT_PRICING: tuple[float, float] = (1.0, 3.0)

_INVITE_EXPIRY_DAYS = 7


# ── Encryption helpers (moved from WorldStitch/ai/user_api_keys.py) ───────────

try:
    from cryptography.fernet import Fernet
    from cryptography.fernet import InvalidToken as _InvalidToken

    _HAS_FERNET = True
except ImportError:
    _HAS_FERNET = False


def _get_fernet():
    if not _HAS_FERNET:
        return None
    secret = os.environ.get("API_KEY_ENCRYPTION_SECRET", "")
    if not secret:
        return None
    return Fernet(secret.encode() if isinstance(secret, str) else secret)


def _encrypt(value: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return value
    return fernet.encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    fernet = _get_fernet()
    if fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except _InvalidToken:
        # Value was stored before encryption was enabled — return as-is.
        return value


# ── Actor: per-call caller identity ───────────────────────────────────────────


@dataclass(frozen=True)
class Actor:
    """The identity a storage call runs as. Never stored on the service."""

    user_id: str = ""
    is_admin: bool = False

    @classmethod
    def from_user(cls, user: User) -> "Actor":
        from server.deps import PLATFORM_ADMIN

        return cls(user_id=str(user.id), is_admin=user.system_role in PLATFORM_ADMIN)


SYSTEM_ACTOR = Actor(user_id="system", is_admin=True)
ANONYMOUS = Actor(user_id="", is_admin=False)


# ── Password helpers (bcrypt is CPU-bound — keep it off the event loop) ───────


def hash_password_sync(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password_sync(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(hash_password_sync, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password_sync, password, password_hash)


# ── Row → model conversion helpers ────────────────────────────────────────────


def _group_to_model(record: GroupRecord) -> Group:
    meta = json.loads(record.meta_json or "{}")
    return Group(
        id=record.id,
        owner_id=record.owner_id,
        name=record.name or "",
        description=record.description or meta.get("description", ""),
        color=record.color or meta.get("color"),
        members=meta.get("members", []),
        member_roles=meta.get("member_roles", {}),
        vault_ids=meta.get("vault_ids", []),
        permissions=meta.get("permissions", {}),
        is_active=meta.get("is_active", True),
    )


def _group_to_metadata(group: Group) -> str:
    return json.dumps(
        {
            "members": getattr(group, "members", []) or [],
            "member_roles": getattr(group, "member_roles", {}) or {},
            "vault_ids": getattr(group, "vault_ids", []) or [],
            "permissions": getattr(group, "permissions", {}) or {},
            "is_active": getattr(group, "is_active", True),
        }
    )


def _char_to_model(record: CharacterRecord) -> Character:
    meta = json.loads(record.meta_json or "{}")
    return Character(
        id=record.id,
        vault_id=record.vault_id or "",
        campaign_id=record.campaign_id,
        name=record.name or meta.get("name", ""),
        description=record.description or meta.get("description"),
        owner_id=meta.get("owner_id", record.created_by or ""),
        is_npc=meta.get("is_npc", False),
        stats=meta.get("stats", {}),
        note_ids=meta.get("note_ids", []),
        ai_memory=meta.get("ai_memory"),
        meta=meta.get("meta", {}),
        is_deleted=meta.get("is_deleted", False),
        created_at=record.created_at or datetime.utcnow(),
        last_modified=record.updated_at or record.created_at or datetime.utcnow(),
    )


def _char_to_metadata(character: Character) -> str:
    return json.dumps(
        {
            "name": character.name or "",
            "description": getattr(character, "description", None),
            "owner_id": getattr(character, "owner_id", ""),
            "is_npc": getattr(character, "is_npc", False),
            "stats": getattr(character, "stats", {}) or {},
            "note_ids": getattr(character, "note_ids", []) or [],
            "ai_memory": getattr(character, "ai_memory", None),
            "meta": getattr(character, "meta", {}) or {},
            "is_deleted": getattr(character, "is_deleted", False),
        }
    )


def _map_to_model(record: MapRecord) -> Map:
    meta = json.loads(record.meta_json or "{}")
    return Map(
        id=record.id,
        vault_id=record.vault_id or "",
        campaign_id=record.campaign_id,
        name=record.name or meta.get("name", ""),
        description=record.description or meta.get("description", ""),
        owner_id=meta.get("owner_id", record.created_by or ""),
        file_path=record.image_url or record.map_url or meta.get("file_path", ""),
        map_type=meta.get("map_type", "region"),
        markers=meta.get("markers", []),
        tags=meta.get("tags", []),
        is_deleted=meta.get("is_deleted", False),
        created_at=record.created_at or datetime.utcnow(),
        last_modified=record.updated_at or record.created_at or datetime.utcnow(),
    )


def _map_to_metadata(map_obj: Map) -> str:
    return json.dumps(
        {
            "name": map_obj.name or "",
            "description": getattr(map_obj, "description", "") or "",
            "owner_id": getattr(map_obj, "owner_id", ""),
            "file_path": getattr(map_obj, "file_path", "") or "",
            "map_type": getattr(map_obj, "map_type", "region") or "region",
            "markers": getattr(map_obj, "markers", []) or [],
            "tags": getattr(map_obj, "tags", []) or [],
            "is_deleted": getattr(map_obj, "is_deleted", False),
        }
    )


def _conversation_to_dict(record: AIConversationRecord) -> dict:
    return {
        "id": record.id,
        "vault_id": record.vault_id,
        "user_id": record.user_id,
        "title": record.title,
        "messages": json.loads(record.messages or "[]"),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _session_log_to_dict(record: SessionLogRecord) -> dict:
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


def _note_rel_to_dict(rec: NoteRelationshipRecord) -> dict:
    return {
        "id": rec.id,
        "vault_id": rec.vault_id,
        "source_note_id": rec.source_note_id,
        "target_note_id": rec.target_note_id,
        "relationship_type": rec.relationship_type,
        "label": rec.label,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "created_by": rec.created_by,
    }


def _require_write(resource, actor_id: Optional[str]) -> None:
    """Raise PermissionError unless actor may write resource (ported semantics)."""
    if actor_id is None or actor_id == "system":
        return
    if actor_id == resource.owner_id:
        return
    granted = (resource.permissions or {}).get(actor_id)
    if granted == "write":
        return
    raise PermissionError(
        f"User '{actor_id}' does not have write access to {type(resource).__name__} '{getattr(resource, 'id', '?')}'"
    )


def _require_delete(resource, actor_id: Optional[str]) -> None:
    if actor_id == "system":
        return
    if actor_id and actor_id == resource.owner_id:
        return
    raise PermissionError(
        f"User '{actor_id}' does not have delete access to {type(resource).__name__} '{getattr(resource, 'id', '?')}'"
    )


# ── The service ───────────────────────────────────────────────────────────────


class AsyncStorage:
    """All database access for the WorldStitch server, async end to end."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        engine: AsyncEngine,
        vault_path: Optional[str] = None,
    ):
        self._sf = session_factory
        self._engine = engine
        self.vault_path: Path = Path(vault_path or ".vault").resolve()
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def _vault_root(self, vault_id: str = "") -> Path:
        if not vault_id:
            return self.vault_path
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", vault_id)
        root = self.vault_path / "_vaults" / safe
        root.mkdir(parents=True, exist_ok=True)
        return root

    # ── Access checks ─────────────────────────────────────────────────────────

    async def _permission_subject_ids(self, session: AsyncSession, actor: Actor) -> set[str]:
        subjects: set[str] = set()
        if not actor.user_id:
            return subjects
        subjects.add(actor.user_id)
        try:
            record = await session.get(UserRecord, actor.user_id)
            if record:
                user = User.model_validate_json(record.data)
                subjects.update(user.groups or [])
        except Exception:
            pass
        return subjects

    async def _can_access(
        self,
        session: AsyncSession,
        actor: Actor,
        owner_id: str,
        permissions: dict,
        member_ids: Optional[list] = None,
    ) -> bool:
        if actor.is_admin:
            return True
        uid = actor.user_id
        if not uid:
            return False
        if uid == owner_id:
            return True
        if uid in (permissions or {}):
            return True
        subjects = await self._permission_subject_ids(session, actor)
        if any(subject in (permissions or {}) for subject in subjects):
            return True
        if member_ids and uid in member_ids:
            return True
        return False

    async def has_vault_access(self, actor: Actor, vault_id: str) -> bool:
        if not vault_id:
            return True
        if actor.is_admin:
            return True
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if not record:
                return vault_id == "default"
            vault = Vault.model_validate_json(record.data)
            if vault.owner_id == actor.user_id:
                return True
            member = await session.scalar(
                select(VaultMemberRecord).where(
                    VaultMemberRecord.vault_id == vault_id,
                    VaultMemberRecord.user_id == actor.user_id,
                )
            )
            return member is not None

    # ========================================================================
    # Users
    # ========================================================================

    async def save_user(self, user: User) -> None:
        email = getattr(user, "email", "") or ""
        system_role = getattr(user, "system_role", "user") or "user"
        async with self._sf() as session:
            record = await session.get(UserRecord, user.id)
            if record:
                record.email = email
                record.system_role = system_role
                record.data = user.model_dump_json()
            else:
                session.add(UserRecord(id=user.id, email=email, system_role=system_role, data=user.model_dump_json()))
            await session.commit()

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        async with self._sf() as session:
            record = await session.get(UserRecord, user_id)
            if record:
                return User.model_validate_json(record.data)
        return None

    async def get_user_by_email(self, email: str) -> Optional[User]:
        async with self._sf() as session:
            record = await session.scalar(select(UserRecord).where(UserRecord.email == email))
            if record:
                return User.model_validate_json(record.data)
            # Fallback: scan rows written before the email column existed
            rows = (await session.scalars(select(UserRecord).where(UserRecord.email.is_(None)))).all()
            for rec in rows:
                user = User.model_validate_json(rec.data)
                if user.email == email:
                    return user
        return None

    async def delete_user_by_id(self, user_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(UserRecord).where(UserRecord.id == user_id))
            await session.commit()
        audit("delete", "user", user_id, user_id="system")

    async def create_user(
        self,
        email: str,
        username: str,
        password: str,
        roles: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
    ) -> User:
        """Create and store a new user with hashed password. Raises ValueError on duplicate email."""
        existing = await self.get_user_by_email(email)
        if existing:
            raise ValueError("Email already in use.")
        password_hash = await hash_password(password)
        user_id = str(uuid.uuid4())
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
        await self.save_user(user)
        audit("update", "user", user.id, user_id=getattr(user, "owner_id", "system"))
        return user

    async def update_user(self, user: User) -> None:
        user.schema_version = max(user.schema_version, 1)
        if not user.last_login:
            user.last_login = datetime.utcnow()
        await self.save_user(user)
        audit("update", "user", user.id, user_id=getattr(user, "owner_id", "system"))

    async def change_password(self, user_id: str, current_password: str, new_password: str) -> None:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found.")
        if not await verify_password(current_password, user.password_hash):
            raise ValueError("Current password is incorrect.")
        if len(new_password) < 8:
            raise ValueError("New password must be at least 8 characters.")
        if current_password == new_password:
            raise ValueError("New password must be different from your current password.")
        user.password_hash = await hash_password(new_password)
        await self.update_user(user)
        audit("update", "user", user.id, user_id=user.id)

    # ========================================================================
    # Groups
    # ========================================================================

    async def save_group(self, group: Group) -> None:
        now = datetime.utcnow()
        async with self._sf() as session:
            record = await session.get(GroupRecord, group.id)
            if record:
                record.owner_id = group.owner_id
                record.name = group.name or ""
                record.description = getattr(group, "description", None)
                record.color = getattr(group, "color", None)
                record.meta_json = _group_to_metadata(group)
                record.updated_at = now
            else:
                session.add(
                    GroupRecord(
                        id=group.id,
                        owner_id=group.owner_id,
                        name=group.name or "",
                        description=getattr(group, "description", None),
                        color=getattr(group, "color", None),
                        meta_json=_group_to_metadata(group),
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.commit()

    async def get_group_by_id(self, group_id: str) -> Optional[Group]:
        async with self._sf() as session:
            record = await session.get(GroupRecord, group_id)
            if record:
                return _group_to_model(record)
        return None

    async def delete_group_by_id(self, group_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(GroupRecord).where(GroupRecord.id == group_id))
            await session.commit()

    async def list_groups(self, actor: Actor) -> List[Group]:
        groups: List[Group] = []
        async with self._sf() as session:
            rows = (await session.scalars(select(GroupRecord))).all()
            for rec in rows:
                try:
                    group = _group_to_model(rec)
                    if not getattr(group, "is_active", True):
                        continue
                    if actor.is_admin or group.owner_id == actor.user_id or actor.user_id in (group.members or []):
                        groups.append(group)
                except Exception:
                    continue
        return groups

    async def create_group(
        self,
        name: str,
        created_by: str,
        description: Optional[str] = None,
        members: Optional[List[str]] = None,
        member_roles: Optional[dict[str, str]] = None,
    ) -> Group:
        group = Group(
            id=str(uuid.uuid4()),
            name=name,
            owner_id=created_by,
            description=description,
            members=members or [],
            member_roles=member_roles or {},
            is_active=True,
            created_at=datetime.utcnow(),
            schema_version=1,
        )
        await self.save_group(group)
        audit("create", "group", group.id, user_id=getattr(group, "owner_id", "system"))
        return group

    async def update_group(self, group: Group) -> None:
        group.schema_version = max(group.schema_version, 1)
        await self.save_group(group)
        audit("update", "group", group.id, user_id=getattr(group, "owner_id", "system"))

    async def delete_group(self, group_id: str) -> None:
        """Soft-delete: flips is_active in the group metadata."""
        group = await self.get_group_by_id(group_id)
        if group:
            group.is_active = False
            await self.update_group(group)

    # ========================================================================
    # Vaults
    # ========================================================================

    async def save_vault(self, vault: Vault) -> None:
        ai_key_shared = bool(getattr(vault, "ai_key_shared", False))
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault.id)
            if record:
                record.owner_id = vault.owner_id
                record.data = vault.model_dump_json()
                record.ai_key_shared = ai_key_shared
            else:
                session.add(
                    VaultRecord(
                        id=vault.id,
                        owner_id=vault.owner_id,
                        data=vault.model_dump_json(),
                        ai_key_shared=ai_key_shared,
                    )
                )
            await session.commit()

    async def get_vault_by_id(self, actor: Actor, vault_id: str) -> Optional[Vault]:
        """Retrieve a Vault by ID — returns None if actor lacks access."""
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if not record:
                return None
            vault = Vault.model_validate_json(record.data)
            vault.ai_key_shared = bool(record.ai_key_shared)
            member = await session.scalar(
                select(VaultMemberRecord).where(
                    VaultMemberRecord.vault_id == vault_id,
                    VaultMemberRecord.user_id == actor.user_id,
                )
            )
            if not member and not actor.is_admin and vault.owner_id != actor.user_id:
                return None
            return vault

    async def get_vault_by_id_for_user(self, vault_id: str, user_id: str) -> Optional[Vault]:
        """Retrieve a Vault by ID, checking vault_members for access."""
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if not record:
                return None
            member = await session.scalar(
                select(VaultMemberRecord).where(
                    VaultMemberRecord.vault_id == vault_id,
                    VaultMemberRecord.user_id == user_id,
                )
            )
            if not member:
                return None
            vault = Vault.model_validate_json(record.data)
            vault.ai_key_shared = bool(record.ai_key_shared)
            return vault

    async def delete_vault_by_id(self, vault_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(VaultMemberRecord).where(VaultMemberRecord.vault_id == vault_id))
            await session.execute(sa_delete(VaultRecord).where(VaultRecord.id == vault_id))
            await session.commit()

    async def list_vaults(self, actor: Actor) -> List[Vault]:
        """Admins see all vaults; regular users see vaults they belong to or own."""
        vaults: List[Vault] = []
        async with self._sf() as session:
            if actor.is_admin:
                records = (await session.scalars(select(VaultRecord))).all()
            else:
                member_rows = (
                    await session.scalars(select(VaultMemberRecord).where(VaultMemberRecord.user_id == actor.user_id))
                ).all()
                member_vault_ids = {m.vault_id for m in member_rows}
                records = (await session.scalars(select(VaultRecord).where(VaultRecord.id.in_(member_vault_ids)))).all()
            for rec in records:
                try:
                    vault = Vault.model_validate_json(rec.data)
                    vault.ai_key_shared = bool(rec.ai_key_shared)
                    if not getattr(vault, "is_active", True):
                        continue
                    vaults.append(vault)
                except Exception:
                    continue
        vaults.sort(key=lambda item: (item.owner_id != (actor.user_id or ""), item.name.lower()))
        return vaults

    async def list_vaults_for_user(self, user_id: str) -> List[Vault]:
        vaults: List[Vault] = []
        async with self._sf() as session:
            member_rows = (
                await session.scalars(select(VaultMemberRecord).where(VaultMemberRecord.user_id == user_id))
            ).all()
            member_vault_ids = {m.vault_id for m in member_rows}
            records = (await session.scalars(select(VaultRecord).where(VaultRecord.id.in_(member_vault_ids)))).all()
            for rec in records:
                try:
                    vault = Vault.model_validate_json(rec.data)
                    vault.ai_key_shared = bool(rec.ai_key_shared)
                    if getattr(vault, "is_active", True):
                        vaults.append(vault)
                except Exception:
                    continue
        return vaults

    async def create_vault(
        self,
        name: str,
        owner_id: str,
        description: Optional[str] = None,
        members: Optional[List[str]] = None,
        settings: Optional[dict] = None,
        permissions: Optional[dict] = None,
        vault_id: Optional[str] = None,
        vault_type: Optional[str] = None,
    ) -> Vault:
        vault = Vault(
            id=vault_id or str(uuid.uuid4()),
            name=name,
            owner_id=owner_id,
            description=description,
            members=members or [],
            settings=settings or {},
            permissions=permissions or {},
            is_active=True,
            created_at=datetime.utcnow(),
            schema_version=1,
            record_version=1,
            vault_type=vault_type or "worldbuilding",
        )
        await self.save_vault(vault)
        audit("create", "vault", vault.id, user_id=owner_id)
        return vault

    async def update_vault(self, vault: Vault) -> None:
        vault.schema_version = max(vault.schema_version, 1)
        vault.record_version += 1
        await self.save_vault(vault)
        audit("update", "vault", vault.id, user_id=getattr(vault, "owner_id", "system"))

    async def delete_vault(self, vault_id: str, actor_id: str = "system") -> None:
        """Soft-delete (is_active=False) after a delete-permission check."""
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if not record:
                return
            vault = Vault.model_validate_json(record.data)
            vault.ai_key_shared = bool(record.ai_key_shared)
        _require_delete(vault, actor_id)
        vault.is_active = False
        await self.update_vault(vault)

    # ── Vault members ─────────────────────────────────────────────────────────

    async def add_vault_member(
        self,
        vault_id: str,
        user_id: str,
        vault_role: str,
        invited_by: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow()
        async with self._sf() as session:
            existing = await session.scalar(
                select(VaultMemberRecord).where(
                    VaultMemberRecord.vault_id == vault_id,
                    VaultMemberRecord.user_id == user_id,
                )
            )
            if existing:
                existing.vault_role = vault_role
            else:
                session.add(
                    VaultMemberRecord(
                        id=str(uuid.uuid4()),
                        vault_id=vault_id,
                        user_id=user_id,
                        vault_role=vault_role,
                        joined_at=now,
                        invited_by=invited_by,
                    )
                )
            await session.commit()

    async def remove_vault_member(self, vault_id: str, user_id: str) -> None:
        async with self._sf() as session:
            await session.execute(
                sa_delete(VaultMemberRecord).where(
                    VaultMemberRecord.vault_id == vault_id,
                    VaultMemberRecord.user_id == user_id,
                )
            )
            await session.commit()

    async def get_vault_member_role(self, vault_id: str, user_id: str) -> Optional[str]:
        async with self._sf() as session:
            member = await session.scalar(
                select(VaultMemberRecord).where(
                    VaultMemberRecord.vault_id == vault_id,
                    VaultMemberRecord.user_id == user_id,
                )
            )
            return member.vault_role if member else None

    async def list_vault_members(self, vault_id: str) -> List[dict]:
        async with self._sf() as session:
            members = (
                await session.scalars(select(VaultMemberRecord).where(VaultMemberRecord.vault_id == vault_id))
            ).all()
            return [
                {
                    "user_id": m.user_id,
                    "vault_role": m.vault_role,
                    "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                    "invited_by": m.invited_by,
                }
                for m in members
            ]

    # ── Vault AI keys ─────────────────────────────────────────────────────────

    async def get_vault_ai_key(self, vault_id: str) -> Optional[str]:
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if record and record.ai_api_key:
                return _decrypt(record.ai_api_key)
        return None

    async def save_vault_ai_key(self, vault_id: str, api_key: str) -> None:
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if record:
                record.ai_api_key = _encrypt(api_key)
                await session.commit()

    async def remove_vault_ai_key(self, vault_id: str) -> None:
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if record:
                record.ai_api_key = None
                await session.commit()

    async def set_vault_ai_sharing(self, vault_id: str, shared: bool) -> None:
        async with self._sf() as session:
            record = await session.get(VaultRecord, vault_id)
            if record:
                record.ai_key_shared = shared
                try:
                    data = json.loads(record.data or "{}")
                    data["ai_key_shared"] = shared
                    record.data = json.dumps(data)
                except Exception:
                    pass
                await session.commit()

    # ========================================================================
    # Folders
    # ========================================================================

    async def save_folder(self, folder: Folder) -> None:
        async with self._sf() as session:
            record = await session.get(FolderRecord, folder.id)
            if record:
                record.data = folder.model_dump_json()
                record.vault_id = getattr(folder, "vault_id", "") or record.vault_id
                record.owner_id = getattr(folder, "owner_id", "") or record.owner_id
            else:
                session.add(
                    FolderRecord(
                        id=folder.id,
                        owner_id=getattr(folder, "owner_id", "") or "",
                        vault_id=getattr(folder, "vault_id", "") or "",
                        data=folder.model_dump_json(),
                    )
                )
            await session.commit()

    async def get_folder_by_id(self, actor: Actor, folder_id: str) -> Optional[Folder]:
        async with self._sf() as session:
            record = await session.get(FolderRecord, folder_id)
            if record:
                folder = Folder.model_validate_json(record.data)
                if folder.vault_id and not await self.has_vault_access(actor, folder.vault_id):
                    return None
                return folder
        return None

    async def delete_folder_by_id(self, folder_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(FolderRecord).where(FolderRecord.id == folder_id))
            await session.commit()
        audit("delete", "folder", folder_id)

    async def list_all_folders(self, actor: Actor, vault_id: str = "") -> List[Folder]:
        results: List[Folder] = []
        async with self._sf() as session:
            rows = (await session.scalars(select(FolderRecord))).all()
            for record in rows:
                try:
                    folder = Folder.model_validate_json(record.data)
                    if vault_id and getattr(folder, "vault_id", "") != vault_id:
                        continue
                    if getattr(folder, "vault_id", "") and not await self.has_vault_access(actor, folder.vault_id):
                        continue
                    results.append(folder)
                except Exception:
                    continue
        return results

    async def create_folder(
        self,
        vault_id: str,
        owner_id: str,
        name: str,
        parent_id: Optional[str] = None,
        description: Optional[str] = None,
        group_id: Optional[str] = None,
        permissions: Optional[dict] = None,
        note_ids: Optional[List[str]] = None,
        meta: Optional[dict] = None,
    ) -> Folder:
        folder = Folder(
            id=str(uuid.uuid4()),
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
        await self.save_folder(folder)
        return folder

    async def update_folder(self, folder: Folder) -> None:
        folder.schema_version = max(folder.schema_version, 1)
        folder.record_version += 1
        folder.last_modified = datetime.utcnow()
        await self.save_folder(folder)

    async def add_note_to_folder(self, actor: Actor, folder_id: str, note_id: str) -> None:
        folder = await self.get_folder_by_id(actor, folder_id)
        if folder and note_id not in folder.note_ids:
            folder.note_ids.append(note_id)
            await self.update_folder(folder)

    async def remove_note_from_folder(self, actor: Actor, folder_id: str, note_id: str) -> None:
        folder = await self.get_folder_by_id(actor, folder_id)
        if folder and note_id in folder.note_ids:
            folder.note_ids.remove(note_id)
            await self.update_folder(folder)

    # ========================================================================
    # Notes
    # ========================================================================

    async def save_note(self, note: Note) -> None:
        """Save or update a Note. Content lives in the data blob + content column."""
        _created_at = getattr(note, "created_at", None)
        _is_deleted = getattr(note, "is_deleted", False)
        _folder = getattr(note, "folder_id", "") or ""
        _title = note.title or ""
        _content = getattr(note, "content", "") or ""
        _tags = " ".join(getattr(note, "tags", []) or [])
        async with self._sf() as session:
            record = await session.get(NoteRecord, note.id)
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
                session.add(
                    NoteRecord(
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
                )
            await session.commit()

    async def get_note_by_id(self, actor: Actor, note_id: str) -> Optional[Note]:
        async with self._sf() as session:
            record = await session.get(NoteRecord, note_id)
            if not record:
                return None
            note = Note.model_validate_json(record.data)
            if note.vault_id and not await self.has_vault_access(actor, note.vault_id):
                return None
            if not await self._can_access(session, actor, note.owner_id, note.permissions or {}):
                return None
            if not actor.is_admin and (getattr(note, "meta", {}) or {}).get("gm_only"):
                return None
            return note

    async def delete_note_by_id(self, note_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(NoteRecord).where(NoteRecord.id == note_id))
            await session.commit()

    async def soft_delete_note(self, note_id: str) -> None:
        async with self._sf() as session:
            record = await session.get(NoteRecord, note_id)
            if record:
                note = Note.model_validate_json(record.data)
                note.is_deleted = True
                note.last_modified = datetime.utcnow()
                record.data = note.model_dump_json()
                record.is_deleted = True  # keep the indexed column in sync
                await session.commit()

    async def list_all_notes(
        self,
        actor: Actor,
        folder: str = "",
        tag: str = "",
        skip: int = 0,
        limit: int = 0,
        vault_id: str = "",  # deprecated alias for campaign_id
        campaign_id: Optional[str] = None,
    ) -> List[Note]:
        filter_id = campaign_id or vault_id or ""
        results: List[Note] = []
        async with self._sf() as session:
            stmt = select(NoteRecord).where(NoteRecord.is_deleted != True)  # noqa: E712
            if filter_id:
                stmt = stmt.where(or_(NoteRecord.campaign_id == filter_id, NoteRecord.vault_id == filter_id))
            if folder:
                stmt = stmt.where(NoteRecord.folder == folder)
            stmt = stmt.order_by(NoteRecord.created_at.desc())
            records = (await session.scalars(stmt)).all()
            for record in records:
                try:
                    note = Note.model_validate_json(record.data)
                    if filter_id:
                        note_cid = getattr(note, "campaign_id", "") or getattr(note, "vault_id", "")
                        if note_cid != filter_id:
                            continue
                    if getattr(note, "vault_id", "") and not await self.has_vault_access(actor, note.vault_id):
                        continue
                    if not await self._can_access(session, actor, note.owner_id, note.permissions or {}):
                        continue
                    if not actor.is_admin and (getattr(note, "meta", {}) or {}).get("gm_only"):
                        continue
                    if tag and tag.lower() not in [t.lower() for t in (note.tags or [])]:
                        continue
                    results.append(note)
                except Exception:
                    continue
        if limit > 0:
            return results[skip : skip + limit]
        return results

    async def count_notes(self, actor: Actor, folder: str = "", vault_id: str = "") -> int:
        async with self._sf() as session:
            stmt = select(func.count()).select_from(NoteRecord).where(NoteRecord.is_deleted.is_not(True))
            if vault_id:
                stmt = stmt.where(NoteRecord.vault_id == vault_id)
            if not actor.is_admin:
                stmt = stmt.where(NoteRecord.owner_id == (actor.user_id or ""))
            return (await session.scalar(stmt)) or 0

    async def update_note_metadata(self, note_id: str, meta: dict) -> None:
        async with self._sf() as session:
            record = await session.get(NoteRecord, note_id)
            if record:
                existing = {}
                try:
                    existing = json.loads(record.data) if record.data else {}
                except Exception:
                    pass
                existing.update(meta)
                record.data = json.dumps(existing)
                await session.commit()

    async def create_note(
        self,
        vault_id: str,
        owner_id: str,
        title: str,
        content: str = "",
        folder_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        group_id: Optional[str] = None,
        permissions: Optional[dict] = None,
        links: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        ai_summary: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> Note:
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
        await self.save_note(note)
        audit("create", "note", note.id, user_id=owner_id)
        return note

    async def update_note(self, note: Note, actor_id: str = "system") -> None:
        _require_write(note, actor_id)
        note.last_modified = datetime.utcnow()
        await self.save_note(note)
        audit("update", "note", note.id, user_id=note.owner_id)

    async def delete_note(self, actor: Actor, note_id: str, actor_id: str = "system") -> None:
        note = await self.get_note_by_id(actor, note_id)
        if note:
            _require_delete(note, actor_id)
        await self.delete_note_by_id(note_id)
        audit("delete", "note", note_id, user_id=actor_id)

    async def add_tag(self, actor: Actor, note_id: str, tag: str) -> None:
        note = await self.get_note_by_id(actor, note_id)
        if note and tag not in note.tags:
            note.tags.append(tag)
            await self.update_note(note)

    async def remove_tag(self, actor: Actor, note_id: str, tag: str) -> None:
        note = await self.get_note_by_id(actor, note_id)
        if note and tag in note.tags:
            note.tags.remove(tag)
            await self.update_note(note)

    # ── Note search ───────────────────────────────────────────────────────────

    async def search_notes(
        self,
        query: str,
        vault_id: str = "",
        top_k: int = 100,
        skip: int = 0,
        limit: int = 0,
        search_type: str = "fulltext",
    ) -> List[Note]:
        """
        Case-insensitive substring match on title and content, DB-backed.

        Replaces the legacy filesystem scan — same return type, but reads
        the denormalised title/content columns so results survive redeploys.
        """
        pattern = f"%{query}%"
        results: List[Note] = []
        async with self._sf() as session:
            stmt = select(NoteRecord).where(
                NoteRecord.is_deleted.is_not(True),
                or_(NoteRecord.title.ilike(pattern), NoteRecord.content.ilike(pattern)),
            )
            if vault_id:
                stmt = stmt.where(NoteRecord.vault_id == vault_id)
            stmt = stmt.limit(top_k)
            records = (await session.scalars(stmt)).all()
            for record in records:
                try:
                    results.append(Note.model_validate_json(record.data))
                except Exception:
                    continue
        if limit > 0:
            return results[skip : skip + limit]
        return results

    async def search_notes_fts(
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
        """PostgreSQL tsvector search with ts_rank; falls back to LIKE on failure."""
        try:
            return await self._search_notes_postgres(query, vault_id, skip, limit, folder, tags, date_from, date_to)
        except Exception as exc:
            logger.warning("Postgres FTS query failed (%s), falling back to LIKE search.", exc)
            return await self._search_notes_like(query, vault_id, skip, limit, folder, tags, date_from, date_to)

    async def _search_notes_postgres(
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
        sql_str = """
            SELECT n.id,
                   n.data,
                   ts_rank(n.search_vector, plainto_tsquery('english', :q)) AS rank,
                   ts_headline('english', COALESCE(n.content, ''),
                               plainto_tsquery('english', :q),
                               'MaxWords=20, MinWords=10, StartSel=<mark>, StopSel=</mark>') AS snippet
            FROM notes n
            WHERE n.is_deleted = false
              AND n.search_vector @@ plainto_tsquery('english', :q)
        """
        params: dict = {"q": query}
        if vault_id:
            sql_str += " AND n.vault_id = :vault_id"
            params["vault_id"] = vault_id
        if folder:
            sql_str += " AND (n.folder = :folder OR n.folder LIKE :folder_prefix)"
            params["folder"] = folder
            params["folder_prefix"] = f"{folder}/%"
        if date_from:
            sql_str += " AND n.created_at >= :date_from"
            params["date_from"] = date_from
        if date_to:
            sql_str += " AND n.created_at <= :date_to"
            params["date_to"] = date_to
        sql_str += " ORDER BY rank DESC LIMIT 10000"

        async with self._sf() as session:
            rows = (await session.execute(text(sql_str), params)).fetchall()

        all_items = []
        for row in rows:
            note_id, data_json, rank, snippet_text = row
            try:
                note = Note.model_validate_json(data_json)
            except Exception:
                continue
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
                    "updated_at": note.last_modified,
                    "score": float(rank),
                    "snippet": snippet_text or "",
                }
            )
        total = len(all_items)
        page = all_items[skip : skip + limit]
        return {"items": page, "total": total, "skip": skip, "limit": limit}

    async def _search_notes_like(
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
        notes_list = await self.search_notes(query, vault_id=vault_id, top_k=10000)
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

    # ========================================================================
    # Characters
    # ========================================================================

    async def save_character(self, character: Character) -> None:
        vault_id = getattr(character, "vault_id", "") or ""
        campaign_id = getattr(character, "campaign_id", None) or vault_id or ""
        now = datetime.utcnow()
        async with self._sf() as session:
            record = await session.get(CharacterRecord, character.id)
            if record:
                record.vault_id = vault_id or record.vault_id
                record.campaign_id = campaign_id or record.campaign_id
                record.name = character.name or ""
                record.description = getattr(character, "description", None)
                record.image_url = getattr(character, "image_url", None)
                record.meta_json = _char_to_metadata(character)
                record.updated_at = now
                if not record.created_by:
                    record.created_by = getattr(character, "owner_id", None)
            else:
                session.add(
                    CharacterRecord(
                        id=character.id,
                        vault_id=vault_id,
                        campaign_id=campaign_id,
                        name=character.name or "",
                        description=getattr(character, "description", None),
                        image_url=getattr(character, "image_url", None),
                        meta_json=_char_to_metadata(character),
                        created_at=now,
                        updated_at=now,
                        created_by=getattr(character, "owner_id", None),
                    )
                )
            await session.commit()

    async def get_character_by_id(self, character_id: str) -> Optional[Character]:
        async with self._sf() as session:
            record = await session.get(CharacterRecord, character_id)
            if record:
                return _char_to_model(record)
        return None

    async def delete_character_by_id(self, character_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(CharacterRecord).where(CharacterRecord.id == character_id))
            await session.commit()
        audit("delete", "character", character_id)

    async def list_characters(
        self,
        vault_id: str = "",  # deprecated alias for campaign_id
        campaign_id: Optional[str] = None,
        char_type: Optional[str] = None,
    ) -> List[Character]:
        filter_id = campaign_id or vault_id or ""
        results: List[Character] = []
        async with self._sf() as session:
            stmt = select(CharacterRecord)
            if filter_id:
                stmt = stmt.where(or_(CharacterRecord.campaign_id == filter_id, CharacterRecord.vault_id == filter_id))
            for rec in (await session.scalars(stmt)).all():
                try:
                    char = _char_to_model(rec)
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

    async def soft_delete_character(self, character_id: str) -> None:
        async with self._sf() as session:
            record = await session.get(CharacterRecord, character_id)
            if record:
                try:
                    meta = json.loads(record.meta_json or "{}")
                    meta["is_deleted"] = True
                    record.meta_json = json.dumps(meta)
                    record.updated_at = datetime.utcnow()
                    await session.commit()
                except Exception:
                    pass

    async def update_character(self, character: Character) -> None:
        character.schema_version = max(character.schema_version, 1)
        character.version += 1
        character.last_modified = datetime.utcnow()
        await self.save_character(character)

    # ========================================================================
    # Maps
    # ========================================================================

    async def save_map(self, map_obj: Map) -> None:
        vault_id = getattr(map_obj, "vault_id", "") or ""
        campaign_id = getattr(map_obj, "campaign_id", None) or vault_id or ""
        now = datetime.utcnow()
        async with self._sf() as session:
            record = await session.get(MapRecord, map_obj.id)
            if record:
                record.vault_id = vault_id or record.vault_id
                record.campaign_id = campaign_id or record.campaign_id
                record.name = map_obj.name or ""
                record.description = getattr(map_obj, "description", None)
                record.image_url = getattr(map_obj, "file_path", None) or None
                record.meta_json = _map_to_metadata(map_obj)
                record.updated_at = now
                if not record.created_by:
                    record.created_by = getattr(map_obj, "owner_id", None)
            else:
                session.add(
                    MapRecord(
                        id=map_obj.id,
                        vault_id=vault_id,
                        campaign_id=campaign_id,
                        name=map_obj.name or "",
                        description=getattr(map_obj, "description", None),
                        image_url=getattr(map_obj, "file_path", None) or None,
                        meta_json=_map_to_metadata(map_obj),
                        created_at=now,
                        updated_at=now,
                        created_by=getattr(map_obj, "owner_id", None),
                    )
                )
            await session.commit()

    async def get_map_by_id(self, map_id: str) -> Optional[Map]:
        async with self._sf() as session:
            record = await session.get(MapRecord, map_id)
            if record:
                return _map_to_model(record)
        return None

    async def delete_map_by_id(self, map_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(MapRecord).where(MapRecord.id == map_id))
            await session.commit()
        audit("delete", "map", map_id)

    async def list_maps(
        self,
        vault_id: str = "",  # deprecated alias for campaign_id
        campaign_id: Optional[str] = None,
        map_type: Optional[str] = None,
    ) -> List[Map]:
        filter_id = campaign_id or vault_id or ""
        results: List[Map] = []
        async with self._sf() as session:
            stmt = select(MapRecord)
            if filter_id:
                stmt = stmt.where(or_(MapRecord.campaign_id == filter_id, MapRecord.vault_id == filter_id))
            for record in (await session.scalars(stmt)).all():
                try:
                    map_obj = _map_to_model(record)
                    if map_obj.is_deleted:
                        continue
                    if map_type and map_obj.map_type != map_type:
                        continue
                    results.append(map_obj)
                except Exception:
                    continue
        return results

    async def soft_delete_map(self, map_id: str) -> None:
        async with self._sf() as session:
            record = await session.get(MapRecord, map_id)
            if record:
                meta = json.loads(record.meta_json or "{}")
                meta["is_deleted"] = True
                record.meta_json = json.dumps(meta)
                record.updated_at = datetime.utcnow()
                await session.commit()

    async def create_map(
        self,
        vault_id: str,
        owner_id: str,
        name: str,
        file_path: str,
        description: Optional[str] = None,
        group_id: Optional[str] = None,
        permissions: Optional[dict] = None,
        tags: Optional[List[str]] = None,
        linked_notes: Optional[List[str]] = None,
        meta: Optional[dict] = None,
    ) -> Map:
        map_obj = Map(
            id=str(uuid.uuid4()),
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
        await self.save_map(map_obj)
        audit("update", "map", map_obj.id, user_id=owner_id)
        return map_obj

    async def update_map(self, map_obj: Map) -> None:
        map_obj.schema_version = max(map_obj.schema_version, 1)
        map_obj.record_version += 1
        map_obj.last_modified = datetime.utcnow()
        await self.save_map(map_obj)
        audit("update", "map", map_obj.id, user_id=getattr(map_obj, "owner_id", "system"))

    # ========================================================================
    # Images / Sounds / Sessions
    # ========================================================================

    async def save_image(self, image: Image) -> None:
        async with self._sf() as session:
            record = await session.get(ImageRecord, image.id)
            if record:
                record.data = image.model_dump_json()
            else:
                session.add(ImageRecord(id=image.id, data=image.model_dump_json()))
            await session.commit()

    async def get_image_by_id(self, image_id: str) -> Optional[Image]:
        async with self._sf() as session:
            record = await session.get(ImageRecord, image_id)
            if record:
                return Image.model_validate_json(record.data)
        return None

    async def delete_image_by_id(self, image_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(ImageRecord).where(ImageRecord.id == image_id))
            await session.commit()

    async def save_sound(self, sound: Sound) -> None:
        async with self._sf() as session:
            record = await session.get(SoundRecord, sound.id)
            if record:
                record.data = sound.model_dump_json()
            else:
                session.add(SoundRecord(id=sound.id, data=sound.model_dump_json()))
            await session.commit()

    async def get_sound_by_id(self, sound_id: str) -> Optional[Sound]:
        async with self._sf() as session:
            record = await session.get(SoundRecord, sound_id)
            if record:
                return Sound.model_validate_json(record.data)
        return None

    async def delete_sound_by_id(self, sound_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(SoundRecord).where(SoundRecord.id == sound_id))
            await session.commit()

    async def save_session(self, session_obj: SessionModel) -> None:
        async with self._sf() as session:
            record = await session.get(SessionRecord, session_obj.id)
            if record:
                record.data = session_obj.model_dump_json()
            else:
                session.add(SessionRecord(id=session_obj.id, data=session_obj.model_dump_json()))
            await session.commit()

    async def get_session_by_id(self, session_id: str) -> Optional[SessionModel]:
        async with self._sf() as session:
            record = await session.get(SessionRecord, session_id)
            if record:
                return SessionModel.model_validate_json(record.data)
        return None

    async def delete_session_by_id(self, session_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(SessionRecord).where(SessionRecord.id == session_id))
            await session.commit()

    async def list_active_sessions(self) -> List[SessionModel]:
        results: List[SessionModel] = []
        async with self._sf() as session:
            for rec in (await session.scalars(select(SessionRecord))).all():
                try:
                    s = SessionModel.model_validate_json(rec.data)
                    if s.is_active and not s.is_expired():
                        results.append(s)
                except Exception:
                    pass
        return results

    # ========================================================================
    # Session Logs
    # ========================================================================

    async def list_session_logs(self, vault_id: str, skip: int = 0, limit: int = 50) -> Tuple[List[dict], int]:
        async with self._sf() as session:
            base = select(SessionLogRecord).where(
                SessionLogRecord.vault_id == vault_id,
                SessionLogRecord.is_deleted == False,  # noqa: E712
            )
            total = (
                await session.scalar(
                    select(func.count())
                    .select_from(SessionLogRecord)
                    .where(
                        SessionLogRecord.vault_id == vault_id,
                        SessionLogRecord.is_deleted == False,  # noqa: E712
                    )
                )
            ) or 0
            records = (
                await session.scalars(base.order_by(SessionLogRecord.session_date.desc()).offset(skip).limit(limit))
            ).all()
            items = [_session_log_to_dict(r) for r in records]
        return items, total

    async def get_session_log(self, session_id: str) -> Optional[dict]:
        async with self._sf() as session:
            record = await session.scalar(
                select(SessionLogRecord).where(
                    SessionLogRecord.id == session_id,
                    SessionLogRecord.is_deleted == False,  # noqa: E712
                )
            )
            if record:
                return _session_log_to_dict(record)
        return None

    async def save_session_log(self, data: dict) -> str:
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
        async with self._sf() as session:
            record = await session.get(SessionLogRecord, session_id)
            if record:
                for field in updatable:
                    if field in data:
                        setattr(record, field, data[field])
                record.updated_at = now
            else:
                session.add(
                    SessionLogRecord(
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
                )
            await session.commit()
        return session_id

    async def soft_delete_session_log(self, session_id: str) -> None:
        async with self._sf() as session:
            record = await session.get(SessionLogRecord, session_id)
            if record:
                record.is_deleted = True
                record.updated_at = datetime.utcnow()
                await session.commit()

    # ========================================================================
    # Starred / Favorites
    # ========================================================================

    async def read_starred(self) -> Set[str]:
        async with self._sf() as session:
            record = await session.get(StarredRecord, "1")
            if record:
                try:
                    return set(json.loads(record.data))
                except (json.JSONDecodeError, TypeError):
                    return set()
        return set()

    async def write_starred(self, stars: Set[str]) -> None:
        async with self._sf() as session:
            record = await session.get(StarredRecord, "1")
            if record:
                record.data = json.dumps(list(stars))
            else:
                session.add(StarredRecord(id="1", data=json.dumps(list(stars))))
            await session.commit()

    # ========================================================================
    # Vault export / import / backup schedule
    # ========================================================================

    async def export_vault_zip(self, actor: Actor, vault_id: str) -> bytes:
        vault = await self.get_vault_by_id(actor, vault_id)
        if not vault:
            raise ValueError("Vault not found")
        notes = await self.list_all_notes(actor, vault_id=vault_id)
        folders = await self.list_all_folders(actor, vault_id=vault_id)

        def _build() -> bytes:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("vault.json", vault.model_dump_json(indent=2))
                zf.writestr(
                    "metadata/notes.json",
                    json.dumps([note.model_dump(mode="json") for note in notes], indent=2, default=str),
                )
                zf.writestr(
                    "metadata/folders.json",
                    json.dumps([folder.model_dump(mode="json") for folder in folders], indent=2, default=str),
                )
            return buffer.getvalue()

        return await asyncio.to_thread(_build)

    async def import_vault_zip(
        self,
        payload: bytes,
        owner_id: str,
        name: Optional[str] = None,
        new_vault_id: Optional[str] = None,
    ) -> Vault:
        def _read() -> tuple[dict, list, list]:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
                vault_data = json.loads(zf.read("vault.json").decode("utf-8"))
                folders = json.loads(zf.read("metadata/folders.json").decode("utf-8"))
                notes = json.loads(zf.read("metadata/notes.json").decode("utf-8"))
            return vault_data, folders, notes

        vault_data, folder_entries, note_entries = await asyncio.to_thread(_read)

        imported_vault = Vault.model_validate(vault_data)
        imported_vault.id = new_vault_id or str(uuid.uuid4())
        imported_vault.owner_id = owner_id
        imported_vault.name = name or f"{imported_vault.name} (Imported)"
        # Imported vault sharing is intentionally cleared so the receiving
        # environment never inherits stale access from the source system.
        imported_vault.members = []
        imported_vault.permissions = {}
        imported_vault.is_active = True
        await self.save_vault(imported_vault)
        await self.add_vault_member(imported_vault.id, owner_id, "owner")

        for entry in folder_entries:
            folder = Folder.model_validate(entry)
            folder.owner_id = owner_id
            folder.vault_id = imported_vault.id
            await self.save_folder(folder)

        for entry in note_entries:
            note = Note.model_validate(entry)
            note.owner_id = owner_id
            note.vault_id = imported_vault.id
            # Imported permissions and group bindings are intentionally reset so
            # the receiving vault never inherits stale access from another system.
            note.permissions = {}
            note.group_id = None
            await self.save_note(note)

        return imported_vault

    async def schedule_vault_backup(self, vault_id: str, cron: str) -> dict[str, Any]:
        settings_path = self._vault_root(vault_id) / ".backup_schedule.json"
        payload = {"vault_id": vault_id, "cron": cron, "updated_at": datetime.utcnow().isoformat()}
        await asyncio.to_thread(settings_path.write_text, json.dumps(payload, indent=2), "utf-8")
        return payload

    # ========================================================================
    # Note relationships (UUID-based typed edges)
    # ========================================================================

    async def create_note_relationship(
        self,
        source_note_id: str,
        target_note_id: str,
        vault_id: str,
        relationship_type: str = "references",
        label: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        now = datetime.utcnow()
        async with self._sf() as session:
            existing = await session.scalar(
                select(NoteRelationshipRecord).where(
                    NoteRelationshipRecord.source_note_id == source_note_id,
                    NoteRelationshipRecord.target_note_id == target_note_id,
                    NoteRelationshipRecord.relationship_type == relationship_type,
                )
            )
            if existing:
                if label is not None:
                    existing.label = label
                    await session.commit()
                return _note_rel_to_dict(existing)
            rec = NoteRelationshipRecord(
                id=str(uuid.uuid4()),
                vault_id=vault_id,
                source_note_id=source_note_id,
                target_note_id=target_note_id,
                relationship_type=relationship_type,
                label=label,
                meta_json="{}",
                created_at=now,
                created_by=created_by,
            )
            session.add(rec)
            await session.commit()
            return _note_rel_to_dict(rec)

    async def get_relationships(self, note_id: str) -> List[str]:
        """Return target note IDs that note_id links to (forward links)."""
        async with self._sf() as session:
            rows = (
                await session.scalars(
                    select(NoteRelationshipRecord).where(NoteRelationshipRecord.source_note_id == note_id)
                )
            ).all()
            return [r.target_note_id for r in rows]

    async def get_backlinks(self, note_id: str) -> List[str]:
        """Return source note IDs of notes that link to note_id (back-links)."""
        async with self._sf() as session:
            rows = (
                await session.scalars(
                    select(NoteRelationshipRecord).where(NoteRelationshipRecord.target_note_id == note_id)
                )
            ).all()
            return [r.source_note_id for r in rows]

    async def upsert_relationship(self, source_note_id: str, target_note_id: str, vault_id: str = "") -> None:
        await self.create_note_relationship(
            source_note_id=source_note_id,
            target_note_id=target_note_id,
            vault_id=vault_id,
            relationship_type="references",
        )

    async def delete_note_relationship(self, rel_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(NoteRelationshipRecord).where(NoteRelationshipRecord.id == rel_id))
            await session.commit()

    async def list_note_relationships(self, vault_id: str, note_id: Optional[str] = None) -> List[dict]:
        async with self._sf() as session:
            stmt = select(NoteRelationshipRecord).where(NoteRelationshipRecord.vault_id == vault_id)
            if note_id:
                stmt = stmt.where(
                    or_(
                        NoteRelationshipRecord.source_note_id == note_id,
                        NoteRelationshipRecord.target_note_id == note_id,
                    )
                )
            return [_note_rel_to_dict(r) for r in (await session.scalars(stmt)).all()]

    # ========================================================================
    # Relationships (typed edge objects)
    # ========================================================================

    async def create_relationship(self, rel: Relationship) -> Relationship:
        now = datetime.utcnow()
        rel.created_at = now
        rel.last_modified = now
        async with self._sf() as session:
            session.add(
                EdgeRecord(
                    id=rel.id,
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    relationship_type=rel.relationship_type,
                    direction=rel.direction,
                    label=rel.label,
                    weight=rel.weight,
                    owner_id=rel.owner_id,
                    vault_id=rel.vault_id,
                    meta=json.dumps(rel.meta or {}),
                    created_at=now,
                    updated_at=now,
                    is_active=True,
                    data=rel.model_dump_json(),
                )
            )
            await session.commit()
        return rel

    async def get_relationship(self, rel_id: str) -> Optional[Relationship]:
        async with self._sf() as session:
            record = await session.scalar(
                select(EdgeRecord).where(
                    EdgeRecord.id == rel_id,
                    EdgeRecord.is_active == True,  # noqa: E712
                )
            )
            if record:
                return Relationship.model_validate_json(record.data)
        return None

    async def list_relationships_for_entity(self, entity_id: str, vault_id: str) -> List[Relationship]:
        results: List[Relationship] = []
        async with self._sf() as session:
            records = (
                await session.scalars(
                    select(EdgeRecord).where(
                        or_(EdgeRecord.source_id == entity_id, EdgeRecord.target_id == entity_id),
                        EdgeRecord.vault_id == vault_id,
                        EdgeRecord.is_active == True,  # noqa: E712
                    )
                )
            ).all()
            for rec in records:
                try:
                    results.append(Relationship.model_validate_json(rec.data))
                except Exception:
                    continue
        return results

    async def list_relationships(self, vault_id: str) -> List[Relationship]:
        results: List[Relationship] = []
        async with self._sf() as session:
            records = (
                await session.scalars(
                    select(EdgeRecord).where(
                        EdgeRecord.vault_id == vault_id,
                        EdgeRecord.is_active == True,  # noqa: E712
                    )
                )
            ).all()
            for rec in records:
                try:
                    results.append(Relationship.model_validate_json(rec.data))
                except Exception:
                    continue
        return results

    async def delete_relationship(self, rel_id: str) -> bool:
        async with self._sf() as session:
            record = await session.get(EdgeRecord, rel_id)
            if not record:
                return False
            record.is_active = False
            record.updated_at = datetime.utcnow()
            await session.commit()
        return True

    async def update_relationship(self, rel_id: str, updates: dict) -> Optional[Relationship]:
        async with self._sf() as session:
            record = await session.scalar(
                select(EdgeRecord).where(
                    EdgeRecord.id == rel_id,
                    EdgeRecord.is_active == True,  # noqa: E712
                )
            )
            if not record:
                return None
            rel = Relationship.model_validate_json(record.data)
            allowed = {"label", "weight", "relationship_type", "direction", "meta"}
            for key, val in updates.items():
                if key in allowed and hasattr(rel, key):
                    setattr(rel, key, val)
            rel.last_modified = datetime.utcnow()
            now = datetime.utcnow()
            record.relationship_type = rel.relationship_type
            record.direction = rel.direction
            record.label = rel.label
            record.weight = rel.weight
            record.meta = json.dumps(rel.meta or {})
            record.updated_at = now
            record.data = rel.model_dump_json()
            await session.commit()
            return rel

    async def relationship_exists(self, source_id: str, target_id: str, vault_id: str, rel_type: str) -> bool:
        async with self._sf() as session:
            record = await session.scalar(
                select(EdgeRecord).where(
                    EdgeRecord.source_id == source_id,
                    EdgeRecord.target_id == target_id,
                    EdgeRecord.vault_id == vault_id,
                    EdgeRecord.relationship_type == rel_type,
                    EdgeRecord.is_active == True,  # noqa: E712
                )
            )
            return record is not None

    # ========================================================================
    # Invite codes
    # ========================================================================

    async def save_invite(self, invite: InviteCode) -> None:
        async with self._sf() as session:
            record = await session.get(InviteRecord, invite.id)
            if record:
                record.code = invite.code.upper()
                record.data = invite.model_dump_json()
            else:
                session.add(InviteRecord(id=invite.id, code=invite.code.upper(), data=invite.model_dump_json()))
            await session.commit()

    async def get_invite_by_code(self, code: str) -> Optional[InviteCode]:
        async with self._sf() as session:
            record = await session.scalar(select(InviteRecord).where(InviteRecord.code == code.strip().upper()))
            if record:
                return InviteCode.model_validate_json(record.data)
        return None

    async def get_invite_by_id(self, invite_id: str) -> Optional[InviteCode]:
        async with self._sf() as session:
            record = await session.get(InviteRecord, invite_id)
            if record:
                return InviteCode.model_validate_json(record.data)
        return None

    async def list_invites(self) -> List[InviteCode]:
        codes: List[InviteCode] = []
        async with self._sf() as session:
            for rec in (await session.scalars(select(InviteRecord))).all():
                try:
                    codes.append(InviteCode.model_validate_json(rec.data))
                except Exception:
                    pass
        return codes

    async def generate_invite(
        self, created_by_user_id: str, expiry_days: int = _INVITE_EXPIRY_DAYS, max_uses: int = 1
    ) -> InviteCode:
        raw = __import__("secrets").token_urlsafe(9)
        raw = raw.upper().replace("-", "A").replace("_", "B")[:12]
        code_str = f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"
        invite = InviteCode(
            owner_id=created_by_user_id,
            code=code_str,
            created_by=created_by_user_id,
            expires_at=datetime.utcnow() + timedelta(days=expiry_days),
            max_uses=max_uses,
        )
        await self.save_invite(invite)
        logger.info(
            "Invite code generated: %s by user %s (expires in %d days, max_uses=%d)",
            code_str,
            created_by_user_id,
            expiry_days,
            max_uses,
        )
        return invite

    async def validate_invite(self, code_str: str) -> Optional[InviteCode]:
        invite = await self.get_invite_by_code(code_str.strip().upper())
        if invite is None:
            return None
        return invite if invite.is_valid() else None

    async def redeem_invite(self, code_str: str, used_by_user_id: str) -> bool:
        invite = await self.get_invite_by_code(code_str.strip().upper())
        if invite is None or not invite.is_valid():
            return False
        invite.use_count += 1
        invite.used_by = used_by_user_id
        await self.save_invite(invite)
        logger.info("Invite %s redeemed by user %s", code_str, used_by_user_id)
        return True

    async def revoke_invite(self, invite_id: str) -> None:
        invite = await self.get_invite_by_id(invite_id)
        if invite:
            invite.is_active = False
            await self.save_invite(invite)
            logger.info("Invite %s revoked", invite_id)

    # ========================================================================
    # Vault invites (email-targeted)
    # ========================================================================

    async def save_vault_invite(self, invite: VaultInvite) -> None:
        async with self._sf() as session:
            record = await session.get(VaultInviteRecord, invite.id)
            if record:
                record.vault_id = invite.vault_id
                record.token = invite.token
                record.data = invite.model_dump_json()
            else:
                session.add(
                    VaultInviteRecord(
                        id=invite.id,
                        vault_id=invite.vault_id,
                        token=invite.token,
                        data=invite.model_dump_json(),
                    )
                )
            await session.commit()

    async def get_vault_invite_by_token(self, token: str) -> Optional[VaultInvite]:
        async with self._sf() as session:
            record = await session.scalar(select(VaultInviteRecord).where(VaultInviteRecord.token == token))
            if record:
                return VaultInvite.model_validate_json(record.data)
        return None

    async def get_vault_invite_by_id(self, invite_id: str) -> Optional[VaultInvite]:
        async with self._sf() as session:
            record = await session.get(VaultInviteRecord, invite_id)
            if record:
                return VaultInvite.model_validate_json(record.data)
        return None

    async def list_vault_invites(self, vault_id: str) -> List[VaultInvite]:
        invites: List[VaultInvite] = []
        async with self._sf() as session:
            rows = (
                await session.scalars(select(VaultInviteRecord).where(VaultInviteRecord.vault_id == vault_id))
            ).all()
            for rec in rows:
                try:
                    invites.append(VaultInvite.model_validate_json(rec.data))
                except Exception:
                    pass
        return invites

    async def delete_vault_invite(self, invite_id: str) -> None:
        async with self._sf() as session:
            await session.execute(sa_delete(VaultInviteRecord).where(VaultInviteRecord.id == invite_id))
            await session.commit()

    # ========================================================================
    # Analytics
    # ========================================================================

    async def save_analytics_event(self, user_id: str, event_type: str, event_data: Optional[dict] = None) -> None:
        async with self._sf() as session:
            session.add(
                AnalyticsEventRecord(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    event_type=event_type,
                    event_data=json.dumps(event_data or {}),
                    created_at=datetime.utcnow(),
                )
            )
            await session.commit()

    async def user_has_analytics_consent(self, user_id: str) -> bool:
        async with self._sf() as session:
            record = await session.get(UserRecord, user_id)
            if record:
                return bool(getattr(record, "analytics_consent", False))
        return False

    async def set_analytics_consent(self, user_id: str, consent: bool) -> None:
        async with self._sf() as session:
            record = await session.get(UserRecord, user_id)
            if record:
                record.analytics_consent = consent
            else:
                session.add(UserRecord(id=user_id, email=None, data="{}", analytics_consent=consent))
            await session.commit()

    async def get_analytics_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
        days: int = 30,
    ) -> List[dict]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with self._sf() as session:
            stmt = select(AnalyticsEventRecord).where(AnalyticsEventRecord.created_at >= cutoff)
            if user_id:
                stmt = stmt.where(AnalyticsEventRecord.user_id == user_id)
            if event_type:
                stmt = stmt.where(AnalyticsEventRecord.event_type == event_type)
            stmt = stmt.order_by(AnalyticsEventRecord.created_at.desc())
            if limit:
                stmt = stmt.limit(limit)
            return [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "event_type": r.event_type,
                    "event_data": json.loads(r.event_data or "{}"),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in (await session.scalars(stmt)).all()
            ]

    async def track(self, event_type: str, user_id: str = "", data: Optional[dict] = None) -> None:
        """Consent-gated analytics tracking. Never raises."""
        if not user_id:
            return
        try:
            if not await self.user_has_analytics_consent(user_id):
                return
            await self.save_analytics_event(user_id, event_type, dict(data or {}))
        except Exception:
            logger.debug("analytics track silently failed for %s / %s", user_id, event_type)

    # ========================================================================
    # AI: per-user API keys + quotas
    # ========================================================================

    async def _get_or_create_api_settings(self, session: AsyncSession, user_id: str) -> UserApiKeyRecord:
        record = await session.get(UserApiKeyRecord, user_id)
        if record is None:
            record = UserApiKeyRecord(
                user_id=user_id,
                openai_api_key=None,
                monthly_request_limit=100,
                requests_this_month=0,
                month_reset_date=date.today().replace(day=1),
            )
            session.add(record)
            await session.flush()
        return record

    async def get_ai_settings(self, user_id: str) -> dict:
        async with self._sf() as session:
            rec = await self._get_or_create_api_settings(session, user_id)
            await session.commit()
            return {
                "has_personal_key": bool(rec.openai_api_key),
                "requests_this_month": rec.requests_this_month,
                "monthly_request_limit": rec.monthly_request_limit,
            }

    async def save_personal_ai_key(self, user_id: str, api_key: str) -> None:
        async with self._sf() as session:
            rec = await self._get_or_create_api_settings(session, user_id)
            rec.openai_api_key = _encrypt(api_key)
            await session.commit()

    async def remove_personal_ai_key(self, user_id: str) -> None:
        async with self._sf() as session:
            rec = await self._get_or_create_api_settings(session, user_id)
            rec.openai_api_key = None
            await session.commit()

    async def get_personal_ai_key(self, user_id: str) -> Optional[str]:
        async with self._sf() as session:
            rec = await session.get(UserApiKeyRecord, user_id)
            if rec is None or rec.openai_api_key is None:
                return None
            return _decrypt(rec.openai_api_key)

    async def check_and_increment_ai_quota(self, user_id: str) -> None:
        """Raise HTTP 429 if the monthly platform-key quota is exhausted."""
        first_of_month = date.today().replace(day=1)
        async with self._sf() as session:
            rec = await self._get_or_create_api_settings(session, user_id)
            if rec.month_reset_date is None or rec.month_reset_date < first_of_month:
                rec.requests_this_month = 0
                rec.month_reset_date = first_of_month
            if rec.requests_this_month >= rec.monthly_request_limit:
                await session.commit()
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=("Monthly AI request limit reached. Add your own OpenAI key in Settings to continue."),
                )
            rec.requests_this_month += 1
            await session.commit()

    async def set_ai_limit(self, user_id: str, monthly_request_limit: int) -> None:
        async with self._sf() as session:
            rec = await self._get_or_create_api_settings(session, user_id)
            rec.monthly_request_limit = monthly_request_limit
            await session.commit()

    async def get_all_ai_usage(self) -> list[dict]:
        async with self._sf() as session:
            records = (await session.scalars(select(UserApiKeyRecord))).all()
            return [
                {
                    "user_id": r.user_id,
                    "has_personal_key": bool(r.openai_api_key),
                    "requests_this_month": r.requests_this_month,
                    "monthly_request_limit": r.monthly_request_limit,
                }
                for r in records
            ]

    # ========================================================================
    # AI: cost tracking
    # ========================================================================

    async def record_ai_usage(
        self,
        user_id: str,
        vault_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        operation: str,
    ) -> None:
        prompt_rate, completion_rate = _PRICING.get(model, _DEFAULT_PRICING)
        cost_usd = (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000
        async with self._sf() as session:
            session.add(
                AIUsageRecord(
                    user_id=user_id,
                    vault_id=vault_id,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    cost_usd=cost_usd,
                    operation=operation,
                    timestamp=datetime.utcnow(),
                )
            )
            await session.commit()

    async def get_user_ai_summary(self, user_id: str, vault_id: Optional[str] = None, days: int = 30) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._sf() as session:
            stmt = select(AIUsageRecord).where(
                AIUsageRecord.user_id == user_id,
                AIUsageRecord.timestamp >= since,
            )
            if vault_id is not None:
                stmt = stmt.where(AIUsageRecord.vault_id == vault_id)
            rows = (await session.scalars(stmt)).all()
        return _aggregate_usage(rows)

    async def get_vault_ai_summary(self, vault_id: str, days: int = 30) -> dict:
        since = datetime.utcnow() - timedelta(days=days)
        async with self._sf() as session:
            rows = (
                await session.scalars(
                    select(AIUsageRecord).where(
                        AIUsageRecord.vault_id == vault_id,
                        AIUsageRecord.timestamp >= since,
                    )
                )
            ).all()
        return _aggregate_usage(rows)

    # ========================================================================
    # AI: conversations
    # ========================================================================

    async def upsert_conversation(
        self,
        conv_id: Optional[str],
        vault_id: str,
        user_id: str,
        title: str,
        messages: list,
    ) -> str:
        now = datetime.utcnow()
        async with self._sf() as session:
            if conv_id:
                record = await session.get(AIConversationRecord, conv_id)
                if record and record.user_id == user_id:
                    record.title = title
                    record.messages = json.dumps(messages)
                    record.updated_at = now
                    await session.commit()
                    return conv_id
            new_id = str(uuid.uuid4())
            session.add(
                AIConversationRecord(
                    id=new_id,
                    vault_id=vault_id,
                    user_id=user_id,
                    title=title,
                    messages=json.dumps(messages),
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()
            return new_id

    async def list_conversations(self, vault_id: str, user_id: str) -> list:
        async with self._sf() as session:
            rows = (
                await session.scalars(
                    select(AIConversationRecord)
                    .where(
                        AIConversationRecord.vault_id == vault_id,
                        AIConversationRecord.user_id == user_id,
                    )
                    .order_by(AIConversationRecord.updated_at.desc())
                    .limit(100)
                )
            ).all()
            return [_conversation_to_dict(r) for r in rows]

    async def get_conversation(self, conv_id: str) -> Optional[dict]:
        async with self._sf() as session:
            record = await session.get(AIConversationRecord, conv_id)
            return _conversation_to_dict(record) if record else None

    async def delete_conversation(self, conv_id: str) -> None:
        async with self._sf() as session:
            record = await session.get(AIConversationRecord, conv_id)
            if record:
                await session.delete(record)
                await session.commit()

    # ========================================================================
    # Campaigns / campaign members / group members / play sessions (raw SQL)
    # ========================================================================

    @staticmethod
    def _slug(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "-", name.lower()).strip("-") or "campaign"

    async def create_campaign(
        self,
        group_id: str,
        owner_user_id: str,
        name: str,
        description: str = "",
        system: str = "",
    ) -> dict:
        campaign_id = str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO campaigns "
                        "(id, group_id, name, slug, description, system, status, "
                        "created_by_user_id, created_at, updated_at) VALUES "
                        "(:id, :gid, :name, :slug, :desc, :sys, 'active', :uid, :now, :now)"
                    ),
                    dict(
                        id=campaign_id,
                        gid=group_id,
                        name=name,
                        slug=self._slug(name),
                        desc=description or "",
                        sys=system or "",
                        uid=owner_user_id,
                        now=now,
                    ),
                )
        except Exception as exc:
            logger.warning("create_campaign failed: %s", exc)
        return await self.get_campaign(campaign_id) or {"id": campaign_id, "group_id": group_id, "name": name}

    @staticmethod
    def _campaign_row_to_dict(row) -> dict:
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

    async def get_campaign(self, campaign_id: str) -> Optional[dict]:
        try:
            async with self._engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT id, group_id, name, slug, description, system, status, "
                            "created_by_user_id, created_at, updated_at, deleted_at "
                            "FROM campaigns WHERE id = :id AND deleted_at IS NULL"
                        ),
                        {"id": campaign_id},
                    )
                ).fetchone()
            if row:
                return self._campaign_row_to_dict(row)
        except Exception as exc:
            logger.warning("get_campaign failed: %s", exc)
        return None

    async def list_campaigns_for_group(self, group_id: str) -> List[dict]:
        try:
            async with self._engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT id, group_id, name, slug, description, system, status, "
                            "created_by_user_id, created_at, updated_at, deleted_at "
                            "FROM campaigns WHERE group_id = :gid AND deleted_at IS NULL "
                            "ORDER BY name"
                        ),
                        {"gid": group_id},
                    )
                ).fetchall()
            return [self._campaign_row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.warning("list_campaigns_for_group failed: %s", exc)
            return []

    async def add_campaign_member(self, campaign_id: str, user_id: str, role: str = "player") -> dict:
        member_id = str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            async with self._engine.begin() as conn:
                # Upsert via delete + insert (portable and explicit)
                await conn.execute(
                    text("DELETE FROM campaign_members WHERE campaign_id = :cid AND user_id = :uid"),
                    {"cid": campaign_id, "uid": user_id},
                )
                await conn.execute(
                    text(
                        "INSERT INTO campaign_members (id, campaign_id, user_id, role, joined_at, created_at) "
                        "VALUES (:id, :cid, :uid, :role, :now, :now)"
                    ),
                    {"id": member_id, "cid": campaign_id, "uid": user_id, "role": role, "now": now},
                )
        except Exception as exc:
            logger.warning("add_campaign_member failed: %s", exc)
        return {"campaign_id": campaign_id, "user_id": user_id, "role": role}

    async def list_campaign_members(self, campaign_id: str) -> List[dict]:
        try:
            async with self._engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT id, campaign_id, user_id, role, joined_at "
                            "FROM campaign_members WHERE campaign_id = :cid"
                        ),
                        {"cid": campaign_id},
                    )
                ).fetchall()
            return [
                {
                    "id": r[0],
                    "campaign_id": r[1],
                    "user_id": r[2],
                    "role": r[3],
                    "joined_at": r[4].isoformat() if r[4] else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("list_campaign_members failed: %s", exc)
            return []

    async def add_group_member(self, group_id: str, user_id: str, role: str = "member") -> dict:
        member_id = str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM group_members WHERE group_id = :gid AND user_id = :uid"),
                    {"gid": group_id, "uid": user_id},
                )
                await conn.execute(
                    text(
                        "INSERT INTO group_members (id, group_id, user_id, role, joined_at) "
                        "VALUES (:id, :gid, :uid, :role, :now)"
                    ),
                    {"id": member_id, "gid": group_id, "uid": user_id, "role": role, "now": now},
                )
        except Exception as exc:
            logger.warning("add_group_member failed: %s", exc)
        return {"group_id": group_id, "user_id": user_id, "role": role}

    async def list_group_members(self, group_id: str) -> List[dict]:
        try:
            async with self._engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text("SELECT id, group_id, user_id, role, joined_at FROM group_members WHERE group_id = :gid"),
                        {"gid": group_id},
                    )
                ).fetchall()
            return [
                {
                    "id": r[0],
                    "group_id": r[1],
                    "user_id": r[2],
                    "role": r[3],
                    "joined_at": r[4].isoformat() if r[4] else None,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("list_group_members failed: %s", exc)
            return []

    async def list_groups_for_user(self, user_id: str) -> List[dict]:
        try:
            async with self._engine.connect() as conn:
                rows = (
                    await conn.execute(
                        text(
                            "SELECT gm.group_id, gm.role, gm.joined_at, g.name, g.owner_id "
                            "FROM group_members gm "
                            "JOIN groups g ON g.id = gm.group_id "
                            "WHERE gm.user_id = :uid"
                        ),
                        {"uid": user_id},
                    )
                ).fetchall()
            return [
                {
                    "group_id": r[0],
                    "role": r[1],
                    "joined_at": r[2].isoformat() if r[2] else None,
                    "name": r[3],
                    "owner_id": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("list_groups_for_user failed: %s", exc)
            return []

    # ── Play sessions ─────────────────────────────────────────────────────────

    @staticmethod
    def _play_session_row_to_dict(row) -> dict:
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

    async def save_play_session(self, campaign_id: str, data: dict) -> str:
        session_id = data.get("id") or str(uuid.uuid4())
        now = datetime.utcnow()
        try:
            async with self._engine.begin() as conn:
                existing = (
                    await conn.execute(text("SELECT id FROM play_sessions WHERE id = :id"), {"id": session_id})
                ).fetchone()
                if existing:
                    updatable = [
                        "title",
                        "session_number",
                        "session_date",
                        "summary",
                        "raw_notes",
                        "ai_recap",
                        "xp_gained",
                        "loot_notes",
                        "status",
                    ]
                    sets = ", ".join(f"{f} = :{f}" for f in updatable if f in data)
                    if sets:
                        params = {f: data[f] for f in updatable if f in data}
                        params["id"] = session_id
                        params["now"] = now
                        await conn.execute(
                            text(f"UPDATE play_sessions SET {sets}, updated_at = :now WHERE id = :id"), params
                        )
                else:
                    await conn.execute(
                        text(
                            "INSERT INTO play_sessions "
                            "(id, campaign_id, created_by_user_id, title, session_number, "
                            "session_date, summary, raw_notes, ai_recap, xp_gained, loot_notes, "
                            "status, created_at, updated_at) VALUES "
                            "(:id, :cid, :uid, :title, :snum, :sdate, :summary, :raw_notes, "
                            ":ai_recap, :xp, :loot, :status, :now, :now)"
                        ),
                        {
                            "id": session_id,
                            "cid": campaign_id,
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
        except Exception as exc:
            logger.warning("save_play_session failed: %s", exc)
        return session_id

    async def get_play_session(self, session_id: str, campaign_id: Optional[str] = None) -> Optional[dict]:
        try:
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
            async with self._engine.connect() as conn:
                row = (await conn.execute(text(sql), params)).fetchone()
            if row:
                return self._play_session_row_to_dict(row)
        except Exception as exc:
            logger.warning("get_play_session failed: %s", exc)
        return None

    async def list_play_sessions(self, campaign_id: str, skip: int = 0, limit: int = 50) -> Tuple[List[dict], int]:
        try:
            async with self._engine.connect() as conn:
                total_row = (
                    await conn.execute(
                        text("SELECT COUNT(*) FROM play_sessions WHERE campaign_id = :cid AND deleted_at IS NULL"),
                        {"cid": campaign_id},
                    )
                ).fetchone()
                total = total_row[0] if total_row else 0
                rows = (
                    await conn.execute(
                        text(
                            "SELECT id, campaign_id, created_by_user_id, title, session_number, "
                            "session_date, summary, raw_notes, ai_recap, xp_gained, loot_notes, "
                            "status, created_at, updated_at "
                            "FROM play_sessions WHERE campaign_id = :cid AND deleted_at IS NULL "
                            "ORDER BY session_date DESC, created_at DESC "
                            "LIMIT :lim OFFSET :off"
                        ),
                        {"cid": campaign_id, "lim": limit, "off": skip},
                    )
                ).fetchall()
            return [self._play_session_row_to_dict(r) for r in rows], total
        except Exception as exc:
            logger.warning("list_play_sessions failed: %s", exc)
            return [], 0

    async def delete_play_session(self, session_id: str, campaign_id: Optional[str] = None) -> None:
        try:
            sql = "UPDATE play_sessions SET deleted_at = :now WHERE id = :id"
            params: dict = {"now": datetime.utcnow(), "id": session_id}
            if campaign_id:
                sql += " AND campaign_id = :cid"
                params["cid"] = campaign_id
            async with self._engine.begin() as conn:
                await conn.execute(text(sql), params)
        except Exception as exc:
            logger.warning("delete_play_session failed: %s", exc)


def _aggregate_usage(rows: list) -> dict:
    total_tokens = 0
    total_cost = 0.0
    by_op: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for r in rows:
        total_tokens += r.total_tokens
        total_cost += r.cost_usd
        by_op[r.operation] = by_op.get(r.operation, 0.0) + r.cost_usd
        by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd
    return {
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "by_operation": by_op,
        "by_model": by_model,
    }
