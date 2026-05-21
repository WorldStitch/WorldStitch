"""Expand schema from 14 legacy tables to 41-table normalized design.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-14

What this migration does
------------------------
Adds 35 new tables that implement the full schema defined in
WorldStitch/storage/schema.py.  The 14 tables created by migrations 0001-0004
(users, groups, vaults, folders, notes, characters, maps, images, sounds,
sessions, session_logs, starred, invite_codes, note_relationships) are left
completely untouched — they remain in place for the existing CRUD layer.
Restructuring those shared tables and migrating their data will happen in a
follow-up PR (PR B).

New tables (35)
---------------
  Identity & auth:  assets, campaigns, refresh_tokens, password_reset_tokens,
                    user_sessions
  Organization:     group_members, group_invites, campaign_invites,
                    campaign_members
  Characters:       character_relationships
  Notes & folders:  note_folders, note_tags, note_tag_assignments,
                    character_notes
  Maps:             map_layers, map_pins
  Sessions:         play_sessions, session_participants
  Timelines:        timelines, timeline_events
  Factions:         factions, faction_memberships
  Locations:        locations, location_connections
  Items:            items, character_items
  Starred:          starred_items
  AI:               ai_conversations, ai_messages, user_ai_settings
  System:           audit_logs, feature_flags, app_settings
  Real-time:        presence, activity_feed

Circular FK note
----------------
assets.campaign_id references campaigns, but campaigns.cover_asset_id
references assets.  We break the cycle by creating assets first with
campaign_id as a plain nullable column (no FK constraint), then creating
campaigns, then adding the FK with batch_alter_table.  SQLite does not
enforce FKs by default, so existing rows are unaffected.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables added by this migration, in reverse-dependency order for teardown.
_NEW_TABLES = [
    "activity_feed",
    "presence",
    "app_settings",
    "feature_flags",
    "audit_logs",
    "user_ai_settings",
    "ai_messages",
    "ai_conversations",
    "starred_items",
    "map_pins",
    "character_items",
    "items",
    "location_connections",
    "locations",
    "faction_memberships",
    "factions",
    "timeline_events",
    "timelines",
    "session_participants",
    "play_sessions",
    "map_layers",
    "character_notes",
    "note_tag_assignments",
    "note_tags",
    "note_folders",
    "character_relationships",
    "campaign_members",
    "campaign_invites",
    "group_invites",
    "group_members",
    "user_sessions",
    "password_reset_tokens",
    "refresh_tokens",
    "campaigns",
    "assets",
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # assets — campaign_id is a plain column here; FK added after campaigns
    # ------------------------------------------------------------------
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False, server_default=sa.text("0")),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("asset_type", sa.String(100), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("thumbnail_key", sa.String(1000), nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assets_group_id", "assets", ["group_id"])
    op.create_index("ix_assets_campaign_id", "assets", ["campaign_id"])
    op.create_index("ix_assets_asset_type", "assets", ["asset_type"])
    op.create_index("ix_assets_deleted_at", "assets", ["deleted_at"])

    # ------------------------------------------------------------------
    # campaigns — references assets (cover_asset_id)
    # ------------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("system", sa.String(200), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("cover_asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("settings", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("group_id", "slug", name="uq_campaigns_group_slug"),
    )
    op.create_index("ix_campaigns_group_id", "campaigns", ["group_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])
    op.create_index("ix_campaigns_deleted_at", "campaigns", ["deleted_at"])

    # Now wire the deferred FK: assets.campaign_id → campaigns.id
    with op.batch_alter_table("assets") as batch_op:
        batch_op.create_foreign_key(
            "fk_assets_campaign_id",
            "campaigns",
            ["campaign_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ------------------------------------------------------------------
    # Auth tokens
    # ------------------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("device_info", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------
    op.create_table(
        "group_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'member'")),
        sa.Column("invited_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),
    )
    op.create_index("ix_group_members_group_id", "group_members", ["group_id"])
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"])

    op.create_table(
        "group_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(32), unique=True, nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_uses", sa.Integer, nullable=True),
        sa.Column("use_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_group_invites_group_id", "group_invites", ["group_id"])
    op.create_index("ix_group_invites_code", "group_invites", ["code"])

    op.create_table(
        "campaign_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(32), unique=True, nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'player'")),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_uses", sa.Integer, nullable=True),
        sa.Column("use_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_campaign_invites_campaign_id", "campaign_invites", ["campaign_id"])
    op.create_index("ix_campaign_invites_code", "campaign_invites", ["code"])

    op.create_table(
        "campaign_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'player'")),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("invited_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_campaign_members_campaign_user"),
    )
    op.create_index("ix_campaign_members_campaign_id", "campaign_members", ["campaign_id"])
    op.create_index("ix_campaign_members_user_id", "campaign_members", ["user_id"])

    # ------------------------------------------------------------------
    # Characters
    # ------------------------------------------------------------------
    op.create_table(
        "character_relationships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_bidirectional", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_char_rels_source_id", "character_relationships", ["source_character_id"])
    op.create_index("ix_char_rels_target_id", "character_relationships", ["target_character_id"])

    # ------------------------------------------------------------------
    # Notes & folders
    # ------------------------------------------------------------------
    op.create_table(
        "note_folders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_folder_id", sa.String(36), sa.ForeignKey("note_folders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("path", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_note_folders_group_id", "note_folders", ["group_id"])
    op.create_index("ix_note_folders_campaign_id", "note_folders", ["campaign_id"])
    op.create_index("ix_note_folders_parent_folder_id", "note_folders", ["parent_folder_id"])

    op.create_table(
        "note_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("group_id", "name", name="uq_note_tags_group_name"),
    )
    op.create_index("ix_note_tags_group_id", "note_tags", ["group_id"])

    op.create_table(
        "note_tag_assignments",
        sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.String(36), sa.ForeignKey("note_tags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_note_tag_assignments_tag_id", "note_tag_assignments", ["tag_id"])

    op.create_table(
        "character_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("character_id", "note_id", name="uq_character_notes_char_note"),
    )
    op.create_index("ix_character_notes_character_id", "character_notes", ["character_id"])
    op.create_index("ix_character_notes_note_id", "character_notes", ["note_id"])

    # ------------------------------------------------------------------
    # Maps
    # ------------------------------------------------------------------
    op.create_table(
        "map_layers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("map_id", sa.String(36), sa.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("layer_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_visible", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("is_gm_only", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("settings", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_map_layers_map_id", "map_layers", ["map_id"])

    # ------------------------------------------------------------------
    # Play sessions
    # ------------------------------------------------------------------
    op.create_table(
        "play_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("session_number", sa.Integer, nullable=True),
        sa.Column("session_date", sa.Date, nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("raw_notes", sa.Text, nullable=True),
        sa.Column("ai_recap", sa.Text, nullable=True),
        sa.Column("xp_gained", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("loot_notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_play_sessions_campaign_id", "play_sessions", ["campaign_id"])
    op.create_index("ix_play_sessions_session_date", "play_sessions", ["session_date"])
    op.create_index("ix_play_sessions_deleted_at", "play_sessions", ["deleted_at"])

    op.create_table(
        "session_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("play_session_id", sa.String(36), sa.ForeignKey("play_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("xp_override", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("play_session_id", "user_id", name="uq_session_participants_session_user"),
    )
    op.create_index("ix_session_participants_play_session_id", "session_participants", ["play_session_id"])

    # ------------------------------------------------------------------
    # Timelines
    # ------------------------------------------------------------------
    op.create_table(
        "timelines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("calendar_system", sa.String(200), nullable=True),
        sa.Column("settings", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_timelines_group_id", "timelines", ["group_id"])
    op.create_index("ix_timelines_campaign_id", "timelines", ["campaign_id"])

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("timeline_id", sa.String(36), sa.ForeignKey("timelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_date_raw", sa.String(200), nullable=True),
        sa.Column("event_date_sort", sa.BigInteger, nullable=True),
        sa.Column("duration_raw", sa.String(200), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("linked_note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_session_id", sa.String(36), sa.ForeignKey("play_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("is_secret", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_timeline_events_timeline_id", "timeline_events", ["timeline_id"])
    op.create_index("ix_timeline_events_sort", "timeline_events", ["event_date_sort"])

    # ------------------------------------------------------------------
    # Factions
    # ------------------------------------------------------------------
    op.create_table(
        "factions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("alignment", sa.String(100), nullable=True),
        sa.Column("disposition", sa.String(100), nullable=True),
        sa.Column("avatar_asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("linked_note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_factions_group_id", "factions", ["group_id"])
    op.create_index("ix_factions_campaign_id", "factions", ["campaign_id"])

    op.create_table(
        "faction_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("faction_id", sa.String(36), sa.ForeignKey("factions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(200), nullable=True),
        sa.Column("rank", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("faction_id", "character_id", name="uq_faction_memberships_faction_char"),
    )
    op.create_index("ix_faction_memberships_faction_id", "faction_memberships", ["faction_id"])
    op.create_index("ix_faction_memberships_character_id", "faction_memberships", ["character_id"])

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------
    op.create_table(
        "locations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_location_id", sa.String(36), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("location_type", sa.String(100), nullable=True),
        sa.Column("population", sa.Integer, nullable=True),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("avatar_asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_map_id", sa.String(36), sa.ForeignKey("maps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_locations_group_id", "locations", ["group_id"])
    op.create_index("ix_locations_campaign_id", "locations", ["campaign_id"])
    op.create_index("ix_locations_parent_id", "locations", ["parent_location_id"])

    op.create_table(
        "location_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_location_id", sa.String(36), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_location_id", sa.String(36), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_type", sa.String(100), nullable=True),
        sa.Column("travel_time", sa.String(200), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_bidirectional", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_location_connections_source", "location_connections", ["source_location_id"])
    op.create_index("ix_location_connections_target", "location_connections", ["target_location_id"])

    # ------------------------------------------------------------------
    # Items & inventory
    # ------------------------------------------------------------------
    op.create_table(
        "items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("item_type", sa.String(100), nullable=True),
        sa.Column("rarity", sa.String(50), nullable=True),
        sa.Column("weight", sa.Float, nullable=True),
        sa.Column("value_gp", sa.Float, nullable=True),
        sa.Column("properties", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("tags", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("linked_note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("avatar_asset_id", sa.String(36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_items_group_id", "items", ["group_id"])
    op.create_index("ix_items_campaign_id", "items", ["campaign_id"])

    op.create_table(
        "character_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("is_equipped", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_character_items_character_id", "character_items", ["character_id"])
    op.create_index("ix_character_items_item_id", "character_items", ["item_id"])

    # ------------------------------------------------------------------
    # Map pins (after map_layers, locations, characters, notes)
    # ------------------------------------------------------------------
    op.create_table(
        "map_pins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("map_id", sa.String(36), sa.ForeignKey("maps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("layer_id", sa.String(36), sa.ForeignKey("map_layers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("label", sa.String(300), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("pin_type", sa.String(100), nullable=True),
        sa.Column("x_position", sa.Float, nullable=False),
        sa.Column("y_position", sa.Float, nullable=False),
        sa.Column("icon", sa.String(200), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("is_gm_only", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("linked_note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_location_id", sa.String(36), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_character_id", sa.String(36), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_map_pins_map_id", "map_pins", ["map_id"])
    op.create_index("ix_map_pins_layer_id", "map_pins", ["layer_id"])

    # ------------------------------------------------------------------
    # Starred items (replaces singleton starred table)
    # ------------------------------------------------------------------
    op.create_table(
        "starred_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_starred_items_user_entity"),
    )
    op.create_index("ix_starred_items_user_id", "starred_items", ["user_id"])
    op.create_index("ix_starred_items_entity", "starred_items", ["entity_type", "entity_id"])

    # ------------------------------------------------------------------
    # AI
    # ------------------------------------------------------------------
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("context_type", sa.String(100), nullable=True),
        sa.Column("context_entity_id", sa.String(36), nullable=True),
        sa.Column("model_id", sa.String(200), nullable=True),
        sa.Column("total_input_tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_output_tokens", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_cost_usd", sa.Numeric(10, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ai_conversations_user_id", "ai_conversations", ["user_id"])
    op.create_index("ix_ai_conversations_campaign_id", "ai_conversations", ["campaign_id"])

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("model_id", sa.String(200), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ai_messages_conversation_id", "ai_messages", ["conversation_id"])

    op.create_table(
        "user_ai_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("personal_api_key_encrypted", sa.Text, nullable=True),
        sa.Column("preferred_model", sa.String(200), nullable=False, server_default=sa.text("'claude-sonnet-4-6'")),
        sa.Column("monthly_limit_usd", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("current_month_usage_usd", sa.Numeric(10, 6), nullable=False, server_default=sa.text("0")),
        sa.Column("current_month_token_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("usage_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("changes", sa.JSON, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'success'")),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_group_id", "audit_logs", ["group_id"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "feature_flags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("rollout_percentage", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("enabled_for_user_ids", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("enabled_for_group_ids", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(200), unique=True, nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_sensitive", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ------------------------------------------------------------------
    # Real-time
    # ------------------------------------------------------------------
    op.create_table(
        "presence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'online'")),
        sa.Column("current_view", sa.String(200), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_presence_campaign_user"),
    )
    op.create_index("ix_presence_campaign_id", "presence", ["campaign_id"])
    op.create_index("ix_presence_last_heartbeat", "presence", ["last_heartbeat_at"])

    op.create_table(
        "activity_feed",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("entity_name", sa.String(500), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_activity_feed_group_created", "activity_feed", ["group_id", "created_at"])
    op.create_index("ix_activity_feed_campaign_created", "activity_feed", ["campaign_id", "created_at"])
    op.create_index("ix_activity_feed_user_id", "activity_feed", ["user_id"])


def downgrade() -> None:
    # Drop in reverse dependency order (leaves the 14 legacy tables intact)
    op.drop_table("activity_feed")
    op.drop_table("presence")
    op.drop_table("app_settings")
    op.drop_table("feature_flags")
    op.drop_table("audit_logs")
    op.drop_table("user_ai_settings")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("starred_items")
    op.drop_table("map_pins")
    op.drop_table("character_items")
    op.drop_table("items")
    op.drop_table("location_connections")
    op.drop_table("locations")
    op.drop_table("faction_memberships")
    op.drop_table("factions")
    op.drop_table("timeline_events")
    op.drop_table("timelines")
    op.drop_table("session_participants")
    op.drop_table("play_sessions")
    op.drop_table("map_layers")
    op.drop_table("character_notes")
    op.drop_table("note_tag_assignments")
    op.drop_table("note_tags")
    op.drop_table("note_folders")
    op.drop_table("character_relationships")
    op.drop_table("campaign_members")
    op.drop_table("campaign_invites")
    op.drop_table("group_invites")
    op.drop_table("group_members")
    op.drop_table("user_sessions")
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_tokens")
    # Remove deferred FK before dropping campaigns/assets
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("fk_assets_campaign_id", type_="foreignkey")
    op.drop_table("campaigns")
    op.drop_table("assets")
