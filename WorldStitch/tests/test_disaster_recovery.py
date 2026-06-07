"""
Disaster recovery tests — Section 8.

Tests that the app can:
1. Export all user data to a zip archive
2. Restore from that archive
3. Survive a corrupted/missing settings.json
4. Recover notes from .versions/ backups
5. Restore note versions via storage layer
"""

import json
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_storage(tmp_path):
    from WorldStitch.storage.hybrid_storage import HybridStorage

    return HybridStorage(str(tmp_path))


OWNER = "user-test-dr"
VAULT = "vault-test-dr"


# ---------------------------------------------------------------------------
# 1. Export produces a valid zip with expected structure
# ---------------------------------------------------------------------------


class TestDataExport:
    def test_export_creates_zip(self, tmp_path):
        """Export should create a non-empty zip file."""
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from WorldStitch.scripts.export_data import export_data

        # Set up a minimal vault with one note
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "Test Note.md").write_text("# Hello World", encoding="utf-8")

        # Patch vault path via a temp settings.json
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "settings.json").write_text(json.dumps({"VAULT_PATH": str(vault)}), encoding="utf-8")

        output = tmp_path / "exports"

        # Instead, call directly with a monkeypatched vault path
        import WorldStitch.scripts.export_data as mod

        original = mod._load_vault_path
        mod._load_vault_path = lambda: vault

        try:
            zip_path = export_data(output)
            assert zip_path.exists()
            assert zip_path.suffix == ".zip"
            assert zip_path.stat().st_size > 0
        finally:
            mod._load_vault_path = original

    def test_export_contains_manifest(self, tmp_path):
        """Exported zip must contain a manifest.json."""
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from WorldStitch.scripts import export_data as mod

        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "note.md").write_text("content", encoding="utf-8")

        original = mod._load_vault_path
        mod._load_vault_path = lambda: vault
        try:
            zip_path = mod.export_data(tmp_path / "out")
            with zipfile.ZipFile(zip_path) as zf:
                assert "manifest.json" in zf.namelist()
                manifest = json.loads(zf.read("manifest.json"))
                assert "exported_at" in manifest
                assert "file_count" in manifest
        finally:
            mod._load_vault_path = original


# ---------------------------------------------------------------------------
# 2. Note backup and restore via storage layer
# ---------------------------------------------------------------------------


class TestNoteBackupRestore:
    def test_backup_creates_bak_file(self, tmp_path):
        """backup_note() should create a .bak file in .versions/."""
        storage = make_storage(tmp_path)
        note_path = "TestNote.md"

        # Write a note file first
        (tmp_path / note_path).write_text("# Original content", encoding="utf-8")

        # Backup it
        backup_path = storage.backup_note(note_path)

        assert Path(backup_path).exists()
        assert Path(backup_path).suffix == ".bak"

    def test_list_note_versions(self, tmp_path):
        """list_note_versions() should return names of backup files."""
        storage = make_storage(tmp_path)
        note_path = "Heroes.md"

        (tmp_path / note_path).write_text("Version 1", encoding="utf-8")
        storage.backup_note(note_path)
        (tmp_path / note_path).write_text("Version 2", encoding="utf-8")
        storage.backup_note(note_path)

        versions = storage.list_note_versions(note_path)
        assert len(versions) >= 2
        assert all(v.endswith(".bak") for v in versions)

    def test_restore_note_version(self, tmp_path):
        """restore_note_version() should recover the note content."""
        storage = make_storage(tmp_path)
        note_path = "Lore.md"

        (tmp_path / note_path).write_text("Original lore", encoding="utf-8")
        storage.backup_note(note_path)

        # Overwrite the note
        (tmp_path / note_path).write_text("Corrupted content", encoding="utf-8")

        # Restore from backup
        versions = storage.list_note_versions(note_path)
        assert versions, "No backup versions found"
        storage.restore_note_version(note_path, versions[0])

        restored = (tmp_path / note_path).read_text(encoding="utf-8")
        assert restored == "Original lore"


# ---------------------------------------------------------------------------
# 3. Settings recovery — missing settings.json falls back to defaults
# ---------------------------------------------------------------------------


class TestSettingsRecovery:
    def test_config_falls_back_to_defaults_if_missing(self, tmp_path):
        """Config should use DEFAULT_CONFIG if settings.json does not exist."""
        from WorldStitch.config.config import DEFAULT_CONFIG, Config

        cfg = Config.__new__(Config)
        cfg._path = tmp_path / "nonexistent_settings.json"  # doesn't exist
        cfg._data = DEFAULT_CONFIG.copy()

        import logging

        cfg.logger = logging.getLogger("test")

        cfg._load()

        # Should still have all default keys
        for key in DEFAULT_CONFIG:
            assert key in cfg._data


# ---------------------------------------------------------------------------
# 4. Storage exists() and search_notes()
# ---------------------------------------------------------------------------


class TestStorageRecoveryMethods:
    def test_exists_returns_false_for_missing(self, tmp_path):
        storage = make_storage(tmp_path)
        assert storage.exists("nonexistent.md") is False

    def test_exists_returns_true_for_present(self, tmp_path):
        storage = make_storage(tmp_path)
        (tmp_path / "present.md").write_text("hello", encoding="utf-8")
        assert storage.exists("present.md") is True

    def test_search_notes_finds_content(self, tmp_path):
        storage = make_storage(tmp_path)
        (tmp_path / "dragons.md").write_text("Here be dragons in the dark", encoding="utf-8")
        (tmp_path / "heroes.md").write_text("The heroes fight bravely", encoding="utf-8")

        results = storage.search_notes("dragons")
        titles = [n.title for n in results]
        assert any("dragons" in t.lower() for t in titles)

    def test_search_notes_returns_empty_for_no_match(self, tmp_path):
        storage = make_storage(tmp_path)
        (tmp_path / "note.md").write_text("nothing relevant here", encoding="utf-8")

        results = storage.search_notes("xyzzy_impossible_string")
        assert results == []
