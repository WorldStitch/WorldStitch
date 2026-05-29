"""
WorldStitch — Comprehensive Database Schema
============================================
Reference implementation using SQLAlchemy 2.x declarative ORM.

This is the canonical schema source-of-truth for all future development.

Design notes:
  - PostgreSQL-only: JSONB for JSON columns, TIMESTAMP for datetimes.
  - All PKs are String(36) UUIDs for portability; migrate to native UUID if needed.
  - Soft deletes via deleted_at timestamp (NULL = active, non-NULL = deleted).
  - Standard metadata: created_at, updated_at, created_by_user_id on all content tables.
  - Three circular FK groups use use_alter=True:
      users.avatar_asset_id  → assets (users precedes assets)
      groups.avatar_asset_id → assets (groups precedes assets)
      assets.campaign_id     → campaigns (assets precedes campaigns)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ===========================================================================
# IDENTITY & AUTH
# ===========================================================================


class User(Base):
    """Registered user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    # use_alter because assets is defined after users
    avatar_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL", use_alter=True, name="fk_users_avatar_asset_id"),
    )
    bio: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_superadmin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
        Index("ix_users_deleted_at", "deleted_at"),
    )


class Group(Base):
    """Workspace / organization that contains campaigns and members."""

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # use_alter because assets is defined after groups
    avatar_asset_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("assets.id", ondelete="SET NULL", use_alter=True, name="fk_groups_avatar_asset_id"),
    )
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_groups_slug", "slug"),
        Index("ix_groups_owner_id", "owner_id"),
        Index("ix_groups_deleted_at", "deleted_at"),
    )


class Asset(Base):
    """
    File metadata for images, audio, PDFs, and video.
    Actual bytes live in object storage (local filesystem today, S3-compatible later).
    storage_key is the object path; thumbnail_key is optional pre-generated thumbnail.
    """

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    # use_alter because campaigns is defined after assets
    campaign_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("campaigns.id", ondelete="SET NULL", use_alter=True, name="fk_assets_campaign_id"),
    )
    uploaded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    # 'image' | 'audio' | 'pdf' | 'video' | 'other'
    asset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_key: Mapped[Optional[str]] = mapped_column(String(1000))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_assets_group_id", "group_id"),
        Index("ix_assets_campaign_id", "campaign_id"),
        Index("ix_assets_asset_type", "asset_type"),
        Index("ix_assets_deleted_at", "deleted_at"),
    )


class Campaign(Base):
    """
    A single ongoing TTRPG game. Scoped to a group.
    system: free-text game system name ('D&D 5e', 'Pathfinder 2e', etc.)
    status: 'active' | 'paused' | 'completed' | 'archived'
    """

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    system: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active", server_default=text("'active'"))
    cover_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("group_id", "slug", name="uq_campaigns_group_slug"),
        Index("ix_campaigns_group_id", "group_id"),
        Index("ix_campaigns_status", "status"),
        Index("ix_campaigns_deleted_at", "deleted_at"),
    )


# ---------------------------------------------------------------------------
# Auth tokens (after users, no further deps)
# ---------------------------------------------------------------------------


class RefreshToken(Base):
    """Long-lived JWT refresh token. Hashed before storage."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    device_info: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )


class PasswordResetToken(Base):
    """Single-use password reset token. Invalidated on use or expiry."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("ix_password_reset_tokens_user_id", "user_id"),)


class UserSession(Base):
    """Active web/app session for presence and concurrent-login tracking."""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )


# ===========================================================================
# ORGANIZATION
# ===========================================================================


class GroupMember(Base):
    """User membership in a group. role: 'owner' | 'admin' | 'member'."""

    __tablename__ = "group_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member", server_default=text("'member'"))
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),
        Index("ix_group_members_group_id", "group_id"),
        Index("ix_group_members_user_id", "user_id"),
    )


class GroupInvite(Base):
    """Shareable invite code that adds a user to a group on redemption."""

    __tablename__ = "group_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    max_uses: Mapped[Optional[int]] = mapped_column(Integer)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_group_invites_group_id", "group_id"),
        Index("ix_group_invites_code", "code"),
    )


# ===========================================================================
# CAMPAIGNS — membership & invites
# ===========================================================================


class CampaignInvite(Base):
    """Shareable invite code that adds a user to a campaign with a preset role."""

    __tablename__ = "campaign_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # role granted on redemption: 'gm' | 'player' | 'observer'
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="player", server_default=text("'player'"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    max_uses: Mapped[Optional[int]] = mapped_column(Integer)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_campaign_invites_campaign_id", "campaign_id"),
        Index("ix_campaign_invites_code", "code"),
    )


# ===========================================================================
# CONTENT — CHARACTERS  (defined before campaign_members to allow FK)
# ===========================================================================


class Character(Base):
    """
    Player character or NPC within a campaign (or group-level world asset).
    campaign_id=NULL means the character belongs to the group's shared world.
    stats is a JSONB blob for system-specific data (HP, AC, ability scores, etc.)
    """

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_npc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    avatar_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    ai_memory: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_characters_group_id", "group_id"),
        Index("ix_characters_campaign_id", "campaign_id"),
        Index("ix_characters_is_npc", "is_npc"),
        Index("ix_characters_deleted_at", "deleted_at"),
    )


class CampaignMember(Base):
    """
    User's membership in a campaign.
    role: 'gm' | 'player' | 'observer'
    character_id links the player to their PC for this campaign.
    """

    __tablename__ = "campaign_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="player", server_default=text("'player'"))
    character_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("characters.id", ondelete="SET NULL"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    invited_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_campaign_members_campaign_user"),
        Index("ix_campaign_members_campaign_id", "campaign_id"),
        Index("ix_campaign_members_user_id", "user_id"),
    )


class CharacterRelationship(Base):
    """
    Directed relationship between two characters ('ally', 'enemy', 'family', etc.)
    is_bidirectional=True means both characters share the same relationship label.
    """

    __tablename__ = "character_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    target_character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_char_rels_source_id", "source_character_id"),
        Index("ix_char_rels_target_id", "target_character_id"),
    )


# ===========================================================================
# CONTENT — NOTES & FOLDERS
# ===========================================================================


class NoteFolder(Base):
    """
    Hierarchical folder for organizing notes.
    parent_folder_id=NULL means top-level folder in the group/campaign.
    path stores a materialized path (e.g. '/parent-id/child-id/') for fast subtree queries.
    """

    __tablename__ = "note_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    parent_folder_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("note_folders.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_note_folders_group_id", "group_id"),
        Index("ix_note_folders_campaign_id", "campaign_id"),
        Index("ix_note_folders_parent_folder_id", "parent_folder_id"),
    )


class Note(Base):
    """
    Freeform markdown note. Content stored inline (not on disk as in v1).
    linked_entity_type + linked_entity_id: polymorphic soft-link to any entity
    (character, location, faction, item, etc.) — indexed for reverse lookup.
    Full-text search via PostgreSQL tsvector trigger.
    """

    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    folder_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("note_folders.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default=text("''"))
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    # polymorphic soft-link: 'character' | 'location' | 'faction' | 'item' | ...
    linked_entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    linked_entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_notes_group_id", "group_id"),
        Index("ix_notes_campaign_id", "campaign_id"),
        Index("ix_notes_folder_id", "folder_id"),
        Index("ix_notes_created_at", "created_at"),
        Index("ix_notes_deleted_at", "deleted_at"),
        Index("ix_notes_linked_entity", "linked_entity_type", "linked_entity_id"),
    )


class NoteTag(Base):
    """Named tag definition scoped to a group. name is unique per group."""

    __tablename__ = "note_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("group_id", "name", name="uq_note_tags_group_name"),
        Index("ix_note_tags_group_id", "group_id"),
    )


class NoteTagAssignment(Base):
    """Many-to-many join between notes and tags."""

    __tablename__ = "note_tag_assignments"

    note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("note_tags.id", ondelete="CASCADE"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("ix_note_tag_assignments_tag_id", "tag_id"),)


class NoteRelationship(Base):
    """
    Directed [[wikilink]] graph between notes.
    relationship_type: 'wikilink' | 'reference' | 'parent' | custom
    Maintained automatically by the backend on every note save.
    """

    __tablename__ = "note_relationships"

    source_note_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    target_note_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="wikilink", server_default=text("'wikilink'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("ix_note_relationships_target", "target_note_id"),)


class CharacterNote(Base):
    """Explicit link between a character and a note (backstory, session recap, etc.)."""

    __tablename__ = "character_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    # 'backstory' | 'session_note' | 'lore' | 'custom'
    relationship_type: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("character_id", "note_id", name="uq_character_notes_char_note"),
        Index("ix_character_notes_character_id", "character_id"),
        Index("ix_character_notes_note_id", "note_id"),
    )


# ===========================================================================
# CONTENT — MAPS
# ===========================================================================


class Map(Base):
    """
    Map definition with an optional background image asset.
    map_type: 'world' | 'region' | 'city' | 'dungeon' | 'encounter' | 'custom'
    """

    __tablename__ = "maps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    map_type: Mapped[Optional[str]] = mapped_column(String(100))
    asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_maps_group_id", "group_id"),
        Index("ix_maps_campaign_id", "campaign_id"),
        Index("ix_maps_deleted_at", "deleted_at"),
    )


class MapLayer(Base):
    """
    Ordered rendering layer on a map (e.g. 'Base', 'Restricted', 'Fog of War').
    is_restricted=True means members cannot see this layer.
    """

    __tablename__ = "map_layers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    map_id: Mapped[str] = mapped_column(String(36), ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    layer_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    is_restricted: Mapped[bool] = mapped_column(
        "is_gm_only", Boolean, nullable=False, default=False, server_default=text("0")
    )
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("ix_map_layers_map_id", "map_id"),)


# ===========================================================================
# CONTENT — PLAY SESSIONS
# ===========================================================================


class PlaySession(Base):
    """
    A single in-person or online game session.
    status: 'planned' | 'completed' | 'cancelled'
    session_number is GM-assigned (not auto-incremented) to allow retroactive logging.
    """

    __tablename__ = "play_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    session_number: Mapped[Optional[int]] = mapped_column(Integer)
    session_date: Mapped[Optional[date]] = mapped_column(Date)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    raw_notes: Mapped[Optional[str]] = mapped_column(Text)
    ai_recap: Mapped[Optional[str]] = mapped_column(Text)
    xp_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    loot_notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planned", server_default=text("'planned'"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_play_sessions_campaign_id", "campaign_id"),
        Index("ix_play_sessions_session_date", "session_date"),
        Index("ix_play_sessions_deleted_at", "deleted_at"),
    )


class SessionParticipant(Base):
    """
    Who attended a play session and with which character.
    display_name is a fallback for players who aren't registered users.
    xp_override lets the GM award different XP per player.
    """

    __tablename__ = "session_participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    play_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("play_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    character_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("characters.id", ondelete="SET NULL"))
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    xp_override: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("play_session_id", "user_id", name="uq_session_participants_session_user"),
        Index("ix_session_participants_play_session_id", "play_session_id"),
    )


# ===========================================================================
# CONTENT — TIMELINES
# ===========================================================================


class Timeline(Base):
    """
    In-game timeline for tracking historical and current events.
    calendar_system: 'gregorian' | 'custom' | or a named fantasy calendar.
    """

    __tablename__ = "timelines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    calendar_system: Mapped[Optional[str]] = mapped_column(String(200))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_timelines_group_id", "group_id"),
        Index("ix_timelines_campaign_id", "campaign_id"),
    )


class TimelineEvent(Base):
    """
    A single event on a timeline.
    event_date_raw: flexible string for in-game dates ('Year 42, Month 3', 'The Third Age').
    event_date_sort: integer representation for ordering (app-defined scale).
    is_secret=True means only the GM sees this event.
    """

    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    timeline_id: Mapped[str] = mapped_column(String(36), ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date_raw: Mapped[Optional[str]] = mapped_column(String(200))
    event_date_sort: Mapped[Optional[int]] = mapped_column(BigInteger)
    duration_raw: Mapped[Optional[str]] = mapped_column(String(200))
    event_type: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    linked_note_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("notes.id", ondelete="SET NULL"))
    linked_session_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("play_sessions.id", ondelete="SET NULL")
    )
    linked_character_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="SET NULL")
    )
    color: Mapped[Optional[str]] = mapped_column(String(20))
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_timeline_events_timeline_id", "timeline_id"),
        Index("ix_timeline_events_sort", "event_date_sort"),
    )


# ===========================================================================
# CONTENT — FACTIONS
# ===========================================================================


class Faction(Base):
    """
    In-game organization, guild, nation, or power group.
    disposition: 'friendly' | 'hostile' | 'neutral' | 'unknown'
    """

    __tablename__ = "factions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    alignment: Mapped[Optional[str]] = mapped_column(String(100))
    disposition: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    linked_note_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("notes.id", ondelete="SET NULL"))
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_factions_group_id", "group_id"),
        Index("ix_factions_campaign_id", "campaign_id"),
    )


class FactionMembership(Base):
    """Character's membership in a faction, including their role and tenure."""

    __tablename__ = "faction_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    faction_id: Mapped[str] = mapped_column(String(36), ForeignKey("factions.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Optional[str]] = mapped_column(String(200))
    rank: Mapped[Optional[str]] = mapped_column(String(200))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("faction_id", "character_id", name="uq_faction_memberships_faction_char"),
        Index("ix_faction_memberships_faction_id", "faction_id"),
        Index("ix_faction_memberships_character_id", "character_id"),
    )


# ===========================================================================
# CONTENT — LOCATIONS
# ===========================================================================


class Location(Base):
    """
    Named place in the game world. Self-referential for hierarchy
    (room → building → city → region → continent).
    location_type: 'continent' | 'region' | 'city' | 'town' | 'dungeon' | 'building' | 'room'
    """

    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    parent_location_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("locations.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    location_type: Mapped[Optional[str]] = mapped_column(String(100))
    population: Mapped[Optional[int]] = mapped_column(Integer)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    avatar_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    linked_map_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("maps.id", ondelete="SET NULL"))
    linked_note_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("notes.id", ondelete="SET NULL"))
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_locations_group_id", "group_id"),
        Index("ix_locations_campaign_id", "campaign_id"),
        Index("ix_locations_parent_id", "parent_location_id"),
    )


class LocationConnection(Base):
    """
    Travel route between two locations.
    connection_type: 'road' | 'river' | 'portal' | 'sea_route' | 'tunnel' | 'custom'
    """

    __tablename__ = "location_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_location_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    target_location_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    connection_type: Mapped[Optional[str]] = mapped_column(String(100))
    travel_time: Mapped[Optional[str]] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_location_connections_source", "source_location_id"),
        Index("ix_location_connections_target", "target_location_id"),
    )


# ===========================================================================
# CONTENT — ITEMS & INVENTORY
# ===========================================================================


class Item(Base):
    """
    Item or inventory entry template. Shared within a group/campaign.
    item_type: 'weapon' | 'armor' | 'potion' | 'misc' | 'currency' | 'magic'
    rarity: 'common' | 'uncommon' | 'rare' | 'very_rare' | 'legendary' | 'artifact'
    value_gp: gold-piece value; scale for other systems via properties JSONB.
    """

    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    item_type: Mapped[Optional[str]] = mapped_column(String(100))
    rarity: Mapped[Optional[str]] = mapped_column(String(50))
    weight: Mapped[Optional[float]] = mapped_column(Float)
    value_gp: Mapped[Optional[float]] = mapped_column(Float)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    linked_note_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("notes.id", ondelete="SET NULL"))
    avatar_asset_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("assets.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_items_group_id", "group_id"),
        Index("ix_items_campaign_id", "campaign_id"),
    )


class CharacterItem(Base):
    """Inventory: a character's ownership of a specific item (with quantity)."""

    __tablename__ = "character_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    is_equipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    acquired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_character_items_character_id", "character_id"),
        Index("ix_character_items_item_id", "item_id"),
    )


# ===========================================================================
# CONTENT — MAP PINS  (after locations, characters, notes)
# ===========================================================================


class MapPin(Base):
    """
    Point-of-interest marker on a map layer.
    pin_type: 'location' | 'character' | 'event' | 'note' | 'custom'
    is_restricted=True hides the pin from members.
    x_position/y_position are normalized [0.0, 1.0] relative to the map image.
    """

    __tablename__ = "map_pins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    map_id: Mapped[str] = mapped_column(String(36), ForeignKey("maps.id", ondelete="CASCADE"), nullable=False)
    layer_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("map_layers.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    label: Mapped[Optional[str]] = mapped_column(String(300))
    description: Mapped[Optional[str]] = mapped_column(Text)
    pin_type: Mapped[Optional[str]] = mapped_column(String(100))
    x_position: Mapped[float] = mapped_column(Float, nullable=False)
    y_position: Mapped[float] = mapped_column(Float, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(200))
    color: Mapped[Optional[str]] = mapped_column(String(20))
    is_restricted: Mapped[bool] = mapped_column(
        "is_gm_only", Boolean, nullable=False, default=False, server_default=text("0")
    )
    linked_note_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("notes.id", ondelete="SET NULL"))
    linked_location_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("locations.id", ondelete="SET NULL")
    )
    linked_character_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="SET NULL")
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_map_pins_map_id", "map_id"),
        Index("ix_map_pins_layer_id", "layer_id"),
    )


# ===========================================================================
# CONTENT — STARRED / FAVORITES
# ===========================================================================


class StarredItem(Base):
    """
    User-specific bookmark on any entity.
    entity_type: 'note' | 'character' | 'map' | 'location' | 'faction' | 'item' | 'session'
    Replaces the v1 singleton JSON blob starred table.
    """

    __tablename__ = "starred_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_starred_items_user_entity"),
        Index("ix_starred_items_user_id", "user_id"),
        Index("ix_starred_items_entity", "entity_type", "entity_id"),
    )


# ===========================================================================
# AI
# ===========================================================================


class AIConversation(Base):
    """
    A persistent AI chat thread, optionally scoped to a campaign or entity.
    context_type hints at what the conversation is about for prompt construction.
    context_type: 'general' | 'character' | 'campaign' | 'note' | 'worldbuilding'
    Token/cost totals are denormalized from child ai_messages for quick display.
    """

    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("groups.id", ondelete="SET NULL"))
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    title: Mapped[Optional[str]] = mapped_column(String(500))
    context_type: Mapped[Optional[str]] = mapped_column(String(100))
    context_entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    model_id: Mapped[Optional[str]] = mapped_column(String(200))
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_ai_conversations_user_id", "user_id"),
        Index("ix_ai_conversations_campaign_id", "campaign_id"),
    )


class AIMessage(Base):
    """
    Individual message in an AI conversation.
    role: 'user' | 'assistant' | 'system'
    Token and cost fields are NULL for user-role messages (no API call).
    """

    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(200))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (Index("ix_ai_messages_conversation_id", "conversation_id"),)


class UserAISettings(Base):
    """
    Per-user AI configuration: API key, preferred model, and monthly spend limits.
    personal_api_key_encrypted: AES-encrypted API key; NULL means use server key.
    monthly_limit_usd=0 means unlimited.
    usage_reset_at: timestamp of the next billing cycle reset.
    """

    __tablename__ = "user_ai_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    personal_api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    preferred_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="claude-sonnet-4-6",
        server_default=text("'claude-sonnet-4-6'"),
    )
    monthly_limit_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    current_month_usage_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    current_month_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    usage_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


# ===========================================================================
# SYSTEM
# ===========================================================================


class AuditLog(Base):
    """
    Immutable event log. Never update or delete rows — append only.
    action uses dot notation: 'user.login', 'note.create', 'campaign.delete'.
    changes: {before: {...}, after: {...}} diff for mutations.
    status: 'success' | 'failure'
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    group_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("groups.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    request_id: Mapped[Optional[str]] = mapped_column(String(100))
    changes: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="success", server_default=text("'success'"))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_group_id", "group_id"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )


class FeatureFlag(Base):
    """
    Runtime feature toggle.
    rollout_percentage: 0-100 for gradual rollout (0=off for all, 100=on for all).
    enabled_for_user_ids / enabled_for_group_ids: explicit allowlists that bypass percentage.
    """

    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    rollout_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    enabled_for_user_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    enabled_for_group_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AppSetting(Base):
    """
    Global key-value configuration store.
    is_sensitive=True means the value should be masked in logs and the admin UI.
    value is JSON to support any scalar or complex setting without schema changes.
    """

    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )


# ===========================================================================
# REAL-TIME
# ===========================================================================


class Presence(Base):
    """
    Live presence record for a user inside a campaign view.
    Maintained by WebSocket heartbeats; stale rows (last_heartbeat_at > 2 min ago) = offline.
    current_view: the route/entity the user is looking at (for "X is editing this note" UI).
    status: 'online' | 'away' | 'busy'
    """

    __tablename__ = "presence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="online", server_default=text("'online'"))
    current_view: Mapped[Optional[str]] = mapped_column(String(200))
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("campaign_id", "user_id", name="uq_presence_campaign_user"),
        Index("ix_presence_campaign_id", "campaign_id"),
        Index("ix_presence_last_heartbeat", "last_heartbeat_at"),
    )


class Relationship(Base):
    """
    First-class typed edge between any two entities within a vault.
    relationship_type: canonical type string from the registry or custom label.
    direction: 'unidirectional' | 'bidirectional'
    weight: AI context relevance 0.0–1.0.
    meta: arbitrary JSON metadata blob.
    """

    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(200), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(30), nullable=False, default="bidirectional", server_default=text("'bidirectional'")
    )
    label: Mapped[Optional[str]] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default=text("1.0"))
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    vault_id: Mapped[str] = mapped_column(String(36), nullable=False)
    meta: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))

    __table_args__ = (
        Index("idx_rel_source", "source_id", "vault_id"),
        Index("idx_rel_target", "target_id", "vault_id"),
        Index("idx_rel_vault", "vault_id", "is_active"),
    )


class ActivityFeed(Base):
    """
    Append-only event stream for the campaign/group activity feed.
    activity_type uses dot notation: 'note.created', 'session.completed', 'character.updated'.
    entity_name is a snapshot of the entity's display name at event time (denormalized).
    Never update or delete rows — the feed is a historical record.
    """

    __tablename__ = "activity_feed"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("groups.id", ondelete="SET NULL"))
    campaign_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("campaigns.id", ondelete="SET NULL"))
    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    activity_type: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(36))
    entity_name: Mapped[Optional[str]] = mapped_column(String(500))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index("ix_activity_feed_group_created", "group_id", "created_at"),
        Index("ix_activity_feed_campaign_created", "campaign_id", "created_at"),
        Index("ix_activity_feed_user_id", "user_id"),
    )
