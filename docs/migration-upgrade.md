# Migration & Upgrade Guide

---

## Upgrading the App

### Standard upgrade

```bash
git pull origin main
pip install -r requirements.txt
```

No manual data migration is required for minor updates. The app's `schema_version` field on each model record tracks the data format version.

### Breaking schema changes

If a future release changes a model's fields in a breaking way:
1. The release notes will include a migration script in `WorldStitch/scripts/`
2. Run the migration script before launching the new version
3. The script will increment `schema_version` on affected records

---

## Data Format

### Notes

Stored as standard Markdown files. Fully compatible with Obsidian and any text editor. No proprietary format.

### Structured data (characters, maps, vaults, etc.)

When using HybridStorage, model data is stored as JSON files in `{VAULT_PATH}/.ws_meta/{model_type}/{id}.json`. Each file is a serialized Pydantic model — human-readable and editable.

When using SQLiteBackend (default), all data lives in `worldstitch.db`.

### Global data (users, groups)

Stored in `~/.worldstitch_ai/users.json` and `~/.worldstitch_ai/groups.json`. These are portable JSON files.

---

## Data Export

Export all user data to a zip archive:

```bash
python WorldStitch/scripts/export_data.py --output exports/
```

The export includes:
- All vault markdown files
- All `.ws_meta/` model JSON files
- `settings.json`
- `audit.log`
- `ai_usage_log.csv`

### Restore from export

```bash
python WorldStitch/scripts/export_data.py --restore exports/worldstitch_export_20260414.zip --target ./my_vault/
```

---

## Moving to a New Machine

1. Export your data: `python WorldStitch/scripts/export_data.py --output exports/`
2. Copy the export zip to the new machine
3. Clone the repo and install dependencies
4. Restore: `python WorldStitch/scripts/export_data.py --restore exports/worldstitch_export.zip --target ./vault/`
5. Update `VAULT_PATH` in `.env`
6. Copy `~/.worldstitch_ai/` from the old machine (contains users/groups)

---

## HybridStorage to SQLiteBackend Migration

The default storage backend is now SQLiteBackend. If you have an existing deployment using HybridStorage (`.ws_meta/` directory):

1. Set `VAULT_TYPE=sqlite` in `.env` or `settings.json`
2. A migration script will read all records from `HybridStorage` and write them to the SQLiteBackend
3. No changes to managers or route handlers are required — they all work through the `StorageBackend` interface
