# Tech Debt Log — MythosEngine

Items logged here are known issues that were not fixed immediately.
Each entry has a severity, description, and the conditions under which it should be resolved.

---

## Active Items

### [LOW] SQLite FTS5 backfill skipped on Postgres path
**Issue:** The `_setup_fts` block that adds legacy columns (`created_at`, `folder`, etc.) to older
SQLite databases only runs when `_is_postgres` is False. A fresh Postgres deployment will have those
columns from Alembic migrations, so this is fine — but any future SQLite-only legacy-column backfills
must remember to keep them inside the `not _is_postgres` branch.
**Fix when:** Legacy SQLite support is dropped entirely.

### [LOW] No mypy type checking configured
**Issue:** Pydantic models are fully typed but the rest of the codebase has no type annotations or
mypy enforcement. Type errors in controllers and managers won't be caught before runtime.
**Fix when:** Section 5 of the foundation checklist.

---

## Resolved Items

| Date | Item | Resolution |
|------|------|------------|
| 2026-04-14 | `file_storage.py` dead code | Deleted |
| 2026-04-14 | API key hardcoded in `settings.json` | Moved to `.env`, key rotated |
| 2026-04-14 | `__pycache__` tracked by git | Added to `.gitignore`, removed from index |
| 2026-04-14 | Black formatter duplicating ruff | Removed black, ruff-format used exclusively |
| 2026-04-14 | All models re-declaring base fields | All models now inherit from `CoreModel` |
| 2026-04-14 | Controllers receiving raw args instead of ctx | All 15 controllers refactored to accept `AppContext` |
| 2026-04-14 | `hybrid_storage.py` using `os.path` throughout | Refactored to `pathlib.Path` |
| 2026-05-05 | HybridStorage is single-vault only | Replaced by `SQLiteBackend` as default backend; each vault has its own DB file |
| 2026-05-05 | No database backend | `SQLiteBackend` (SQLAlchemy 2.0) implemented and wired via `StorageRouter` |
| 2026-05-05 | `controller_browse.py` using `storage.vault_path` directly | `absolute_path(rel)` added to `StorageBackend`; controller updated |
| 2026-05-05 | Version restore reads `.bak` directly | `storage.restore_note_version()` now called from controller |
| 2026-05-05 | `storage_router.py` unused | `AppContext` now uses `StorageRouter`; backend selected from `config.VAULT_TYPE` |
| 2026-05-05 | Stray scripts in project root | Moved to `scripts/` |
| 2026-05-05 | `backup_note` timestamp collision (second resolution) | Switched to microsecond precision (`%Y%m%d-%H%M%S-%f`) in both backends |
