# Backup & Restore

MythosEngine automatically backs up notes before any update or delete operation. This document explains how backups work and how to restore them.

---

## Automatic Backups

Every time a note is updated or deleted through `NoteManager`, a backup is created automatically before the change is applied. Backups are stored as `.bak` files inside a hidden `.versions/` folder in your vault.

### Backup location

```
{VAULT_PATH}/
└── .versions/
    └── {folder}/
        └── {note-name}.md.20260414-143022.bak
```

Timestamp format: `YYYYMMDD-HHMMSS`

### Backup limits

Up to 20 backup versions are retained per note. Older versions are pruned automatically.

---

## Restoring a Note Version

### From the GUI

1. Open the **Browse** tab
2. Select a note
3. Click **History** (version history button)
4. Select a version from the list
5. Click **Restore**

### Manually

Copy a `.bak` file over the original `.md` file:

```powershell
# Example — restore a note from a specific backup
Copy-Item ".versions\NPCs\Gandalf.md.20260414-143022.bak" "NPCs\Gandalf.md"
```

---

## Crash Recovery

If the app crashes while editing, unsaved content is written to:

```
{PROJECT_ROOT}/recovery/
└── recovery_chat_{timestamp}.txt
```

These files are plain text and can be opened in any editor.

---

## Full Data Export

To export all your data (notes, models, logs, settings) as a zip archive:

```bash
python MythosEngine/scripts/export_data.py --output exports/
```

This creates a timestamped zip file containing:
- All vault markdown files
- All `.dnd_meta/` structured model data
- `settings.json`
- `audit.log`
- `ai_usage_log.csv`

See [Data Portability](migration-upgrade.md#data-export) for details.

---

## Disaster Recovery

### Scenario: vault folder deleted or corrupted

1. Restore your vault from OS backup or cloud sync (Obsidian sync, OneDrive, etc.)
2. Point `VAULT_PATH` in `.env` or `settings.json` to the restored location
3. Launch the app — `.dnd_meta/` will be regenerated from existing note files on next access

### Scenario: settings.json lost

The app recreates `settings.json` with defaults on next launch. Re-enter your vault path and API key.

### Scenario: restoring from a full export

```bash
python MythosEngine/scripts/export_data.py --restore exports/mythos_export_20260414.zip --target ./restored_vault/
```
