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
1. The release notes will include a migration script in `MythosEngine/scripts/`
2. Run the migration script before launching the new version
3. The script will increment `schema_version` on affected records

---

## Data Format

### Notes

Stored as standard Markdown files. Fully compatible with Obsidian and any text editor. No proprietary format.

### Structured data (characters, maps, vaults, etc.)

Stored as JSON files in `{VAULT_PATH}/.dnd_meta/{model_type}/{id}.json`. Each file is a serialized Pydantic model — human-readable and editable.

### Global data (users, groups)

Stored in `~/.mythos_engine_ai/users.json` and `~/.mythos_engine_ai/groups.json`. These are portable JSON files.

---

## Data Export

Export all user data to a zip archive:

```bash
python MythosEngine/scripts/export_data.py --output exports/
```

The export includes:
- All vault markdown files
- All `.dnd_meta/` model JSON files
- `settings.json`
- `audit.log`
- `ai_usage_log.csv`

### Restore from export

```bash
python MythosEngine/scripts/export_data.py --restore exports/mythos_export_20260414.zip --target ./my_vault/
```

---

## Moving to a New Machine

1. Export your data: `python MythosEngine/scripts/export_data.py --output exports/`
2. Copy the export zip to the new machine
3. Clone the repo and install dependencies
4. Restore: `python MythosEngine/scripts/export_data.py --restore exports/ward_dnd_export.zip --target ./vault/`
5. Update `VAULT_PATH` in `.env`
6. Copy `~/.mythos_engine_ai/` from the old machine (contains users/groups)

---

## Future: Database Migration

When the storage backend is upgraded from file-based to SQLite or PostgreSQL:

1. A new `SQLiteStorageBackend` (or `PostgresStorageBackend`) will be added to `storage/`
2. A migration script will read all records from `HybridStorage` and write them to the new backend
3. `AppContext.__init__` will be updated to use the new backend
4. No changes to managers, controllers, or views are required — they all work through the `StorageBackend` interface
