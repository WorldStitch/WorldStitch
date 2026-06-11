"""
SQLAlchemy ORM models for WorldStitch — the single source of truth for
table mappings used by the async server.

IMPORTANT: several tables have a column literally named "metadata"
(added by migration 0017). SQLAlchemy's Declarative API reserves the
``metadata`` attribute on mapped classes, so those columns are mapped
under the Python attribute ``meta_json`` while keeping the database
column name "metadata":

    meta_json: Mapped[str] = mapped_column("metadata", Text, ...)

Never rename the column itself — only the Python-side attribute differs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all WorldStitch ORM models."""


class UserRecord(Base):
    """ORM model for User data — stored as JSON blob."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob
    analytics_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
    system_role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", server_default="user")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())


class EmailVerificationTokenRecord(Base):
    """Single-use email verification token."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PasswordResetTokenRecord(Base):
    """Single-use password reset token."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class GroupRecord(Base):
    """ORM model for Group — explicit columns + metadata JSON for rich fields."""

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # metadata stores members, member_roles, vault_ids, permissions, is_active, etc.
    meta_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}", server_default="{}")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class VaultRecord(Base):
    """ORM model for Vault data — stored as JSON blob."""

    __tablename__ = "vaults"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob
    # AI key columns — managed separately from the JSON blob to keep keys encrypted at rest
    ai_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_key_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
    # Vault Brain — per-vault persistent AI context document
    brain_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brain_edit_role: Mapped[str] = mapped_column(String(20), nullable=False, default="admin", server_default="admin")


class VaultMemberRecord(Base):
    """Normalised vault membership — one row per (vault, user) pair."""

    __tablename__ = "vault_members"
    __table_args__ = (
        Index("ix_vault_members_vault_id", "vault_id"),
        Index("ix_vault_members_user_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    vault_role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    joined_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    invited_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class FolderRecord(Base):
    """ORM model for Folder data — stored as JSON blob."""

    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class NoteRecord(Base):
    """ORM model for Note — JSON blob plus denormalised columns for search."""

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
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob (full Note model)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    folder: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, default="")
    # Denormalised columns for PostgreSQL tsvector search — populated in save_note()
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="")
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # The search_vector (tsvector) and embedding (pgvector) columns exist in the
    # table but are intentionally unmapped — they are only touched via raw SQL.


class CharacterRecord(Base):
    """ORM model for Character — explicit columns + metadata JSON for rich fields."""

    __tablename__ = "characters"
    __table_args__ = (Index("ix_characters_vault_id", "vault_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", server_default="")
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # metadata stores is_npc, stats, note_ids, ai_memory, meta, is_deleted, owner_id, etc.
    meta_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}", server_default="{}")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class MapRecord(Base):
    """ORM model for Map — explicit columns + metadata JSON for rich fields."""

    __tablename__ = "maps"
    __table_args__ = (Index("ix_maps_vault_id", "vault_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", server_default="")
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="", server_default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    map_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # metadata stores map_type, markers, tags, is_deleted, owner_id, etc.
    meta_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}", server_default="{}")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


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
    """ORM model for session log — normalized columns for queryability."""

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


class VaultInviteRecord(Base):
    """ORM model for VaultInvite — email-targeted vault membership invitation."""

    __tablename__ = "vault_invites"
    __table_args__ = (Index("ix_vault_invites_vault_id", "vault_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob


class NoteRelationshipRecord(Base):
    """Explicit typed relationship between two notes within a vault."""

    __tablename__ = "note_relationships"
    __table_args__ = (
        Index("ix_note_rels_vault_id", "vault_id"),
        Index("ix_note_rels_source_note_id", "source_note_id"),
        Index("ix_note_rels_target_note_id", "target_note_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    source_note_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_note_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(200), nullable=False, default="references")
    label: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    meta_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, default="{}", server_default="{}")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class EdgeRecord(Base):
    """First-class typed edge between any two entities within a vault."""

    __tablename__ = "relationships"
    __table_args__ = (
        Index("idx_rel_source", "source_id", "vault_id"),
        Index("idx_rel_target", "target_id", "vault_id"),
        Index("idx_rel_vault", "vault_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    relationship_type: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    direction: Mapped[str] = mapped_column(
        String(30), nullable=False, default="bidirectional", server_default="bidirectional"
    )
    label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1.0")
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    meta: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # full JSON blob


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


class AIConversationRecord(Base):
    """Persisted AI chat conversation — messages stored as a JSON array."""

    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("ix_ai_conversations_vault_id", "vault_id"),
        Index("ix_ai_conversations_user_id", "user_id"),
        Index("ix_ai_conversations_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Untitled")
    messages: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserApiKeyRecord(Base):
    """One row per user — stores personal API key and monthly quota state."""

    __tablename__ = "user_api_settings"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Encrypted at rest via Fernet when API_KEY_ENCRYPTION_SECRET is set.
    openai_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monthly_request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    requests_this_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    month_reset_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class AIUsageRecord(Base):
    """One row per AI API call — stores token counts and computed cost."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    vault_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    operation: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
