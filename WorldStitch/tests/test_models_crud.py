"""
CRUD smoke tests for all WorldStitch data models.

These tests verify:
1. Every model can be instantiated with required fields
2. CoreModel fields (id, schema_version, owner_id, created_at, last_modified) are present
3. Models reject unknown fields (extra="forbid")
4. Models can be round-tripped through JSON (serialize + deserialize)
"""

import json

import pytest

OWNER = "user-test-001"
VAULT = "vault-test-001"


# ---------------------------------------------------------------------------
# CoreModel field contract
# ---------------------------------------------------------------------------


def assert_core_fields(obj):
    """Every model must have these fields from CoreModel."""
    assert hasattr(obj, "id") and obj.id
    assert hasattr(obj, "schema_version") and obj.schema_version >= 1
    assert hasattr(obj, "owner_id") and obj.owner_id == OWNER
    assert hasattr(obj, "created_at") and obj.created_at is not None
    assert hasattr(obj, "last_modified") and obj.last_modified is not None


def assert_json_roundtrip(obj):
    """Model must survive a JSON serialize/deserialize cycle."""
    cls = type(obj)
    data = json.loads(obj.model_dump_json())
    restored = cls.model_validate(data)
    assert restored.id == obj.id
    assert restored.owner_id == obj.owner_id


# ---------------------------------------------------------------------------
# Note
# ---------------------------------------------------------------------------


class TestNoteModel:
    def test_create(self):
        from WorldStitch.models.note import Note

        note = Note(owner_id=OWNER, vault_id=VAULT, title="Test Note")
        assert note.title == "Test Note"
        assert note.content == ""
        assert_core_fields(note)

    def test_json_roundtrip(self):
        from WorldStitch.models.note import Note

        note = Note(owner_id=OWNER, vault_id=VAULT, title="Roundtrip Note", content="hello")
        assert_json_roundtrip(note)

    def test_rejects_unknown_fields(self):
        from WorldStitch.models.note import Note

        with pytest.raises(Exception):
            Note(owner_id=OWNER, vault_id=VAULT, title="X", unknown_field="bad")

    def test_soft_delete_flag(self):
        from WorldStitch.models.note import Note

        note = Note(owner_id=OWNER, vault_id=VAULT, title="Delete me")
        assert note.is_deleted is False
        note.is_deleted = True
        assert note.is_deleted is True


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------


class TestCharacterModel:
    def test_create(self):
        from WorldStitch.models.character import Character

        char = Character(owner_id=OWNER, vault_id=VAULT, name="Gandalf")
        assert char.name == "Gandalf"
        assert char.is_npc is False
        assert_core_fields(char)

    def test_npc_flag(self):
        from WorldStitch.models.character import Character

        npc = Character(owner_id=OWNER, vault_id=VAULT, name="Innkeeper", is_npc=True)
        assert npc.is_npc is True

    def test_json_roundtrip(self):
        from WorldStitch.models.character import Character

        char = Character(owner_id=OWNER, vault_id=VAULT, name="Frodo", stats={"hp": 20})
        assert_json_roundtrip(char)


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------


class TestVaultModel:
    def test_create(self):
        from WorldStitch.models.vault import Vault

        vault = Vault(owner_id=OWNER, name="Middle Earth")
        assert vault.name == "Middle Earth"
        assert vault.is_active is True
        assert_core_fields(vault)

    def test_json_roundtrip(self):
        from WorldStitch.models.vault import Vault

        vault = Vault(owner_id=OWNER, name="The Shire")
        assert_json_roundtrip(vault)


# ---------------------------------------------------------------------------
# Folder
# ---------------------------------------------------------------------------


class TestFolderModel:
    def test_create(self):
        from WorldStitch.models.folder import Folder

        folder = Folder(owner_id=OWNER, vault_id=VAULT, name="NPCs")
        assert folder.name == "NPCs"
        assert folder.parent_id is None
        assert_core_fields(folder)

    def test_nested_folder(self):
        from WorldStitch.models.folder import Folder

        parent = Folder(owner_id=OWNER, vault_id=VAULT, name="Characters")
        child = Folder(owner_id=OWNER, vault_id=VAULT, name="Villains", parent_id=parent.id)
        assert child.parent_id == parent.id


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class TestGroupModel:
    def test_create(self):
        from WorldStitch.models.group import Group

        group = Group(owner_id=OWNER, name="The Fellowship")
        assert group.name == "The Fellowship"
        assert group.is_active is True
        assert_core_fields(group)

    def test_member_roles(self):
        from WorldStitch.models.group import Group

        group = Group(
            owner_id=OWNER,
            name="Party",
            members=["u1", "u2"],
            member_roles={"u1": "gm", "u2": "player"},
        )
        assert group.member_roles["u1"] == "gm"


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class TestUserModel:
    def test_create(self):
        from WorldStitch.models.user import User

        user = User(
            id="u-001",
            owner_id="u-001",
            email="test@example.com",
            username="testuser",
            password_hash="hashed_password_123",
        )
        assert user.email == "test@example.com"
        assert user.is_active is True

    def test_invalid_email(self):
        from WorldStitch.models.user import User

        with pytest.raises(Exception):
            User(
                id="u-002",
                owner_id="u-002",
                email="not-an-email",
                username="bad",
                password_hash="hashed_password_123",
            )


# ---------------------------------------------------------------------------
# Map, Image, Sound
# ---------------------------------------------------------------------------


class TestAssetModels:
    def test_map_create(self):
        from WorldStitch.models.map import Map

        m = Map(owner_id=OWNER, vault_id=VAULT, name="Region Map", file_path="maps/region.png")
        assert m.name == "Region Map"
        assert_core_fields(m)

    def test_image_create(self):
        from WorldStitch.models.image import Image

        img = Image(owner_id=OWNER, vault_id=VAULT, file_path="images/npc.png")
        assert img.is_public is True
        assert_core_fields(img)

    def test_sound_create(self):
        from WorldStitch.models.sound import Sound

        snd = Sound(owner_id=OWNER, vault_id=VAULT, name="Tavern Ambience", file_path="sounds/tavern.mp3")
        assert snd.name == "Tavern Ambience"
        assert_core_fields(snd)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class TestSessionModel:
    def test_create_and_expiry(self):
        from datetime import datetime, timedelta

        from WorldStitch.models.session import Session

        expires = datetime.utcnow() + timedelta(hours=1)
        session = Session(owner_id=OWNER, expires_at=expires)
        assert session.is_active is True
        assert session.is_expired() is False

    def test_expired_session(self):
        from datetime import datetime, timedelta

        from WorldStitch.models.session import Session

        past = datetime.utcnow() - timedelta(hours=1)
        session = Session(owner_id=OWNER, expires_at=past)
        assert session.is_expired() is True
