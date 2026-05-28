# MythosEngine — Full Codebase Audit Report

**Date:** 2026-05-20  
**Scope:** All Python, JSX/JS, Markdown, YAML, config, and env files  
**Status:** Read-only; no changes made

---

## Severity Key

| Level | Meaning |
|---|---|
| **HIGH** | Breaks something, causes misleading behavior, or is actively wrong |
| **MEDIUM** | Dead weight — safe but wastes space or creates confusion |
| **LOW** | Cosmetic / doc-only |

---

## 1. Dead Code / Unused Files

| Sev | File | Issue |
|---|---|---|
| **HIGH** | `frontend/src/pages/Groups.jsx` | Imported in `App.jsx:18` but no route ever mounts it; `/groups` redirects to `/vaults` (App.jsx:255). Orphaned component. |
| **MEDIUM** | `MythosEngine/auth/login_dialog.py` | Qt6 GUI dialog; only referenced by itself (its own `if TYPE_CHECKING` guard). Never called from the FastAPI server. |
| **MEDIUM** | `MythosEngine/auth/signup_dialog.py` | Qt6 GUI dialog; only referenced by `login_dialog.py:181`. Never called from the FastAPI server. |
| **MEDIUM** | `MythosEngine/auth/setup_wizard.py` | Qt6 setup wizard; not imported anywhere outside itself. |
| **MEDIUM** | `MythosEngine/utils/crash_handler.py` | 709-line Qt6 crash reporter; not imported from the FastAPI server or any active entrypoint. Only referenced from within `smtp_reporter.py`. |
| **MEDIUM** | `MythosEngine/utils/smtp_reporter.py` | Email crash reporter; only imported by `crash_handler.py` (also unused). Circular dead cluster. |

---

## 2. Stale Terminology

### 2a. Old project name (`Ward_DND_AI`) — code / CI

| Sev | File | Line | Issue |
|---|---|---|---|
| **HIGH** | `.github/workflows/ci.yml` | 28 | `pytest Ward_DND_AI/tests/` — path doesn't exist; CI test step fails on missing directory |
| **HIGH** | `.github/workflows/ci.yml` | 31 | `mypy Ward_DND_AI/models/ Ward_DND_AI/managers/ ...` — same dead path; mypy type check is skipped |
| **MEDIUM** | `MythosEngine/context/app_context.py` | 81–88 | Migration comment and variable `ward_dnd.db` (the migration logic itself is useful but the old name lives in code) |

### 2b. Old project name — docs / config (LOW unless linked from README)

| Sev | File | Lines | Issue |
|---|---|---|---|
| **LOW** | `TESTER_GUIDE.md` | 11, 14, 149, 153, 164, 195 | References "D&D dungeon masters", "NPCs", "DM notes", "D&D campaign" |
| **LOW** | `.project/todo.md` | 1, 33, 58, 78, 100, 102, 116, 124 | Titled "Ward DND AI → World Builder"; uses GM/player/NPC throughout |
| **LOW** | `.project/dev_checklist.md` | 14, 20 | `python -m unittest discover -s Ward_DND_AI/tests`, `python Ward_DND_AI/main.py` |
| **LOW** | `docs/backup-restore.md` | 3, 67, 72, 87, 96 | "Ward DND AI", `Ward_DND_AI/scripts/`, `.dnd_meta/` paths |
| **LOW** | `docs/config-reference.md` | 3, 34, 40, 76 | "Ward DND AI", `Ward_DND_AI/config/settings.json`, `APP_NAME: Ward DND AI` |
| **LOW** | `docs/migration-upgrade.md` | 19, 33, 37, 46, 51, 59, 66, 69, 71 | `Ward_DND_AI/scripts/`, `.dnd_meta/`, `~/.ward_dnd_ai/` paths throughout |
| **LOW** | `docs/permissions-model.md` | 3, 38, 53 | "Ward DND AI", `from Ward_DND_AI.auth.permission_checker import permissions`, `local@ward-dnd.local` |

### 2c. `is_gm` / `ROLE_GM` in business logic

| Sev | File | Lines | Issue |
|---|---|---|---|
| **HIGH** | `MythosEngine/auth/permissions.py` | 16–22 | `ROLE_GM = "gm"`, `ROLE_PLAYER = "player"` constants; `ALL_ROLES` tuple uses old role names |
| **HIGH** | `MythosEngine/auth/permissions.py` | 44–56 | `is_gm()` and `is_gm_or_admin()` functions exported as public API |
| **HIGH** | `MythosEngine/context/app_context.py` | 141–153 | `is_gm()` and `is_gm_or_admin()` methods on AppContext |
| **HIGH** | `MythosEngine/storage/storage_base.py` | 36–58 | `_is_gm: bool` attribute; `set_user_context(..., is_gm=False)` signature |
| **HIGH** | `MythosEngine/storage/sqlite_backend.py` | 468, 515, 803, 883, 920, 935, 1743 | Seven `_is_gm` checks gating content visibility |
| **MEDIUM** | `MythosEngine/storage/schema.py` | 446, 545, 913, 930, 1467, 1490 | `is_gm_only` column in ORM models + docstrings saying "players cannot see this" |
| **MEDIUM** | `MythosEngine/managers/group_manager.py` | 80 | `role in {"gm", permission}` hardcoded role string |
| **MEDIUM** | `MythosEngine/models/group.py` | 39 | Docstring: `Maps user_id -> role string (e.g. 'gm', 'player', 'observer')` |
| **MEDIUM** | `MythosEngine/config/note_templates.yaml` | 1–2 | Template key `NPC:`, description `"D&D non-player character"` |

### 2d. `"player"` / `"gm"` hardcoded in server routes

| Sev | File | Lines | Issue |
|---|---|---|---|
| **HIGH** | `server/routes/auth.py` | 258 | Seed admin created with `roles=["admin", "gm"]` — initializes with old GM role |
| **HIGH** | `server/routes/auth.py` | 357, 464, 492, 498, 512 | Five places defaulting to `"player"` role string for new/returning users |
| **MEDIUM** | `server/routes/campaigns.py` | 53 | `role: str = Field("player", pattern="^(gm|player|observer)$")` |
| **MEDIUM** | `server/routes/campaigns.py` | 125 | `add_campaign_member(..., role="gm")` hardcoded |
| **MEDIUM** | `server/routes/groups.py` | 41 | `role: str = Field("player", min_length=2, max_length=32)` default |
| **MEDIUM** | `server/routes/users.py` | 193 | `normalized_roles = ["player"]` fallback |

### 2e. `"player"` / `"gm"` in frontend

| Sev | File | Lines | Issue |
|---|---|---|---|
| **MEDIUM** | `frontend/src/api.js` | 335 | `addMember(id, user_id, role = "player")` default parameter |
| **MEDIUM** | `frontend/src/components/settings/AccountSettings.jsx` | 14–15 | Fallback role display: `return u?.role || 'player'` |
| **MEDIUM** | `frontend/src/components/settings/AdminSettings.jsx` | 9, 271, 360 | `ROLE_PLAYER = 'player'` constant; used in Badge variant comparisons |
| **MEDIUM** | `frontend/src/pages/OwnerGroups.jsx` | 18, 151, 166 | `useState('player')` default; `<option value="player">player</option>`; display fallback `|| 'player'` |
| **LOW** | `frontend/src/pages/Groups.jsx` | 305 | Display fallback `|| 'player'` (moot since component is dead — see §1) |
| **LOW** | `frontend/src/pages/Characters.jsx` | 49, 54, 314, 418 | `char_type === 'player'` / `'npc'` — these are character-type enum values, not user roles; the displayed "PC"/"NPC" labels are intentional, but the underlying strings are D&D-flavored |

---

## 3. Broken Wiring

| Sev | File | Lines | Issue |
|---|---|---|---|
| **HIGH** | `.github/workflows/ci.yml` | 28, 31 | Tests and type-checks run against `Ward_DND_AI/` path that doesn't exist — pytest fails on the missing test path, and mypy is non-blocking due to `continue-on-error: true` |
| **MEDIUM** | `MythosEngine/context/app_context.py` | 23 | `from MythosEngine.auth.permission_checker import PermissionChecker` — this file exists and is used, but `permission_checker.py` is a minimal legacy shim; the active logic is in `permissions.py`. Two parallel permission systems. |

---

## 4. Outdated Config / Dependencies

### 4a. `requirements.txt` — unused packages

| Sev | Package | Line | Reason |
|---|---|---|---|
| **MEDIUM** | `banks==2.1.2` | 11 | Not imported anywhere in the codebase (grepped all `.py` files — zero hits) |
| **MEDIUM** | `tkhtmlview==0.3.1` | 101 | Tkinter HTML widget; not imported anywhere. Leftover from pre-Qt6 era. |

### 4b. `requirements.txt` — large framework with partial use

| Sev | Package | Lines | Reason |
|---|---|---|---|
| **LOW** | `llama-index==0.12.42` + 11 sub-packages | 41–55 | Only `llama_index.core` (index_manager.py) and a guard import in `vector_index.py` are used. `llama-cloud`, `llama-cloud-services`, `llama-parse`, and all OpenAI-variant sub-packages are not directly imported. Worth auditing whether all 12 packages are needed. |

### 4c. Docs referencing removed/renamed paths

| Sev | File | Issue |
|---|---|---|
| **MEDIUM** | `docs/backup-restore.md` | All script paths use `Ward_DND_AI/scripts/export_data.py`; the script lives at `MythosEngine/scripts/export_data.py` |
| **MEDIUM** | `docs/migration-upgrade.md` | Same — all commands use old module path |
| **MEDIUM** | `docs/config-reference.md` | Config location listed as `Ward_DND_AI/config/settings.json` |
| **MEDIUM** | `docs/permissions-model.md` | Import example uses `from Ward_DND_AI.auth.permission_checker import permissions` |

---

## 5. TODO / FIXME Comments

| Sev | File | Line | Comment |
|---|---|---|---|
| **MEDIUM** | `MythosEngine/ai/user_api_keys.py` | 31 | `# TODO: encrypt at rest` — API keys stored in plaintext |

No other TODO/FIXME/HACK/XXX found in `.py`, `.jsx`, or `.js` files.

---

## 6. Debug / Placeholder Code

No bare `console.log` debug statements found in frontend JS/JSX (only `console.error` / `console.warn` in legitimate error handlers).

No rogue `print()` statements in server route handlers.

| Sev | File | Lines | Issue |
|---|---|---|---|
| **LOW** | `MythosEngine/tests/test_summarize.py` | Throughout | Uses `print()` statements for test output instead of pytest assertions; not a server concern but makes CI output noisy |
| **LOW** | `server/app.py` | 142–149 | CORS allows `localhost:5173` / `127.0.0.1:5173` hardcoded — expected for Electron dev, but should be env-driven for production |

---

## Summary Table

| Category | HIGH | MEDIUM | LOW |
|---|---|---|---|
| Dead code / unused files | 1 | 5 | 0 |
| Stale terminology (code) | 8 | 15 | 3 |
| Stale docs / config | 0 | 6 | 7 |
| Broken wiring | 1 | 1 | 0 |
| Dead dependencies | 0 | 2 | 1 |
| TODOs | 0 | 1 | 0 |
| Debug / placeholder | 0 | 0 | 2 |
| **Total** | **10** | **30** | **13** |

---

## Recommended Fix Order

1. **Fix CI immediately** — `.github/workflows/ci.yml` runs tests/mypy on a path that doesn't exist, so neither step does anything. Update paths to `MythosEngine/` and `server/`.
2. **Delete `Groups.jsx`** — imported but never mounted; remove the dead import from `App.jsx` too.
3. **Rename the role system** — `ROLE_GM`/`ROLE_PLAYER` in `permissions.py` and all downstream uses. Decide on canonical role names (`vault_admin`/`member`? or keep `gm`/`player` as domain terms) and do a targeted rename.
4. **Remove dead deps** — drop `banks` and `tkhtmlview` from `requirements.txt`.
5. **Remove legacy Qt6 cluster** — `login_dialog.py`, `signup_dialog.py`, `setup_wizard.py`, `crash_handler.py`, `smtp_reporter.py` are a self-contained dead cluster in the FastAPI server context. Delete or quarantine.
6. **Update docs** — bulk find-and-replace `Ward_DND_AI` → `MythosEngine` across all `docs/` and `.project/` files.
7. **Encrypt API keys** — resolve the TODO in `user_api_keys.py:31`.
