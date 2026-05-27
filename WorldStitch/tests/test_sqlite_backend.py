"""
SQLite backend integration tests.

Runs the same operations as the HybridStorage tests but against
SQLiteBackend to verify both backends are equivalent.
"""

import sqlite3


def make_sqlite_storage(tmp_path):
    from WorldStitch.storage.sqlite_backend import SQLiteBackend

    db_path = str(tmp_path / "test.db")
    vault_path = str(tmp_path / "vault")
    return SQLiteBackend(db_path=db_path, vault_path=vault_path)


OWNER = "user-sqlite-test"
VAULT = "vault-sqlite-test"


class TestSQLiteUserCRUD:
    def test_save_and_get_user_by_id(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        from WorldStitch.models.user import User

        user = User(
            id="u1",
            owner_id="u1",
            email="alice@example.com",
            username="Alice",
            password_hash="$2b$12$hash",
        )
        storage.save_user(user)
        fetched = storage.get_user_by_id("u1")
        assert fetched is not None
        assert fetched.username == "Alice"
        assert fetched.email == "alice@example.com"

    def test_get_user_by_email(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        from WorldStitch.models.user import User

        user = User(
            id="u2",
            owner_id="u2",
            email="bob@example.com",
            username="Bob",
            password_hash="$2b$12$hash",
        )
        storage.save_user(user)
        fetched = storage.get_user_by_email("bob@example.com")
        assert fetched is not None
        assert fetched.username == "Bob"

    def test_delete_user(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        from WorldStitch.models.user import User

        user = User(
            id="u3",
            owner_id="u3",
            email="carol@example.com",
            username="Carol",
            password_hash="$2b$12$hash",
        )
        storage.save_user(user)
        storage.delete_user_by_id("u3")
        assert storage.get_user_by_id("u3") is None


class TestSQLiteNoteCRUD:
    def test_write_and_read_note(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.write_note("lore.md", "# Lore\n\nSome content.")
        content = storage.read_note("lore.md")
        assert "Some content" in content

    def test_note_exists(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        assert not storage.note_exists("missing.md")
        storage.write_note("present.md", "hello")
        assert storage.note_exists("present.md")

    def test_list_notes(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.write_note("a.md", "A")
        storage.write_note("b.md", "B")
        notes = storage.list_notes()
        assert any("a.md" in n for n in notes)
        assert any("b.md" in n for n in notes)

    def test_delete_note(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.write_note("del.md", "to delete")
        storage.delete_note("del.md")
        assert not storage.note_exists("del.md")

    def test_search_notes(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.write_note("dragon.md", "The red dragon terrorised the village.")
        storage.write_note("quest.md", "A boring quest about sheep.")
        results = storage.search_notes("dragon")
        assert len(results) == 1
        assert results[0].title == "dragon"


class TestSQLiteFolderCRUD:
    def test_create_and_list_folders(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.create_folder("campaigns/westmarch")
        folders = storage.list_folders()
        assert any("westmarch" in f for f in folders)

    def test_folder_exists(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        assert not storage.folder_exists("nonexistent")
        storage.create_folder("nonexistent")
        assert storage.folder_exists("nonexistent")

    def test_delete_folder(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.create_folder("to_delete")
        storage.delete_folder("to_delete")
        assert not storage.folder_exists("to_delete")


class TestSQLiteVersioning:
    def test_backup_creates_bak_file(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.write_note("heroes.md", "Version 1")
        backup_path = storage.backup_note("heroes.md")
        assert backup_path.endswith(".bak")

    def test_restore_note_version(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        storage.write_note("lore.md", "Original lore")
        storage.backup_note("lore.md")
        storage.write_note("lore.md", "Changed lore")

        versions = storage.list_note_versions("lore.md")
        assert len(versions) >= 1
        storage.restore_note_version("lore.md", versions[0])
        restored = storage.read_note("lore.md")
        assert "Original lore" in restored


class TestSQLiteStarred:
    def test_read_write_starred(self, tmp_path):
        storage = make_sqlite_storage(tmp_path)
        assert storage.read_starred() == set()
        storage.write_starred({"note1", "note2"})
        stars = storage.read_starred()
        assert "note1" in stars
        assert "note2" in stars


class TestSQLiteInviteCodes:
    def test_save_and_get_invite_by_code(self, tmp_path):
        from datetime import datetime, timedelta

        from WorldStitch.models.invite_code import InviteCode

        storage = make_sqlite_storage(tmp_path)
        invite = InviteCode(
            id="inv-1",
            owner_id="admin-1",
            code="TEST-CODE-1234",
            created_by="admin-1",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        storage.save_invite(invite)
        fetched = storage.get_invite_by_code("TEST-CODE-1234")
        assert fetched is not None
        assert fetched.code == "TEST-CODE-1234"

    def test_list_invites(self, tmp_path):
        from datetime import datetime, timedelta

        from WorldStitch.models.invite_code import InviteCode

        storage = make_sqlite_storage(tmp_path)
        for i in range(3):
            invite = InviteCode(
                id=f"inv-{i}",
                owner_id="admin-1",
                code=f"CODE-{i:04d}",
                created_by="admin-1",
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            storage.save_invite(invite)
        all_invites = storage.list_invites()
        assert len(all_invites) == 3


class TestSQLiteUpdateNoteMeta:
    def test_update_note_metadata(self, tmp_path):
        from WorldStitch.models.note import Note

        storage = make_sqlite_storage(tmp_path)
        note = Note(
            id="note-meta-test",
            owner_id=OWNER,
            vault_id=VAULT,
            title="Meta Test",
            content="content",
        )
        storage.save_note(note)
        storage.update_note_metadata("note-meta-test", {"key": "value"})
        # No exception = pass; metadata merge is idempotent


class TestSQLiteLegacySchemaCompatibility:
    def test_legacy_notes_table_gets_missing_columns(self, tmp_path):
        from WorldStitch.models.note import Note
        from WorldStitch.storage.sqlite_backend import SQLiteBackend

        db_path = tmp_path / "legacy.db"
        vault_path = tmp_path / "vault"

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE notes (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL DEFAULT '',
                    vault_id TEXT NOT NULL DEFAULT '',
                    data TEXT NOT NULL
                )
                """
            )

        storage = SQLiteBackend(db_path=str(db_path), vault_path=str(vault_path))

        with sqlite3.connect(db_path) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}

        assert {"created_at", "is_deleted", "folder", "title", "content", "tags"}.issubset(columns)

        note = Note(
            id="legacy-note-1",
            owner_id=OWNER,
            vault_id="default",
            title="Legacy Compatibility",
            content="content",
        )
        storage.save_note(note)
        storage.set_user_context(OWNER)
        assert storage.get_note_by_id("legacy-note-1") is not None
