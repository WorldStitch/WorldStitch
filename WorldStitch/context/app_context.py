"""
AppContext — the single service locator for the entire WorldStitch application.

Every controller and view should receive an AppContext instance rather than
importing managers or storage directly. This keeps dependencies explicit,
makes testing easy (swap out storage/managers via constructor), and gives
a clear picture of what services exist at runtime.

Multiuser design:
- All managers share the same StorageBackend instance so writes are consistent.
- The AI engine is set after construction (main.py wires it up) so startup
  order remains flexible.
- A 'current_user_id' slot is provided for single-user mode; the full auth
  flow will replace this with proper session-based identity later.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from WorldStitch.auth.auth_manager import AuthManager
from WorldStitch.auth.permission_checker import PermissionChecker
from WorldStitch.auth.session_manager import SessionManager as AuthSessionManager
from WorldStitch.config.config import Config
from WorldStitch.managers.character_manager import CharacterManager
from WorldStitch.managers.folder_manager import FolderManager
from WorldStitch.managers.group_manager import GroupManager
from WorldStitch.managers.invite_manager import InviteManager
from WorldStitch.managers.map_manager import MapManager
from WorldStitch.managers.note_manager import NoteManager
from WorldStitch.managers.user_manager import UserManager
from WorldStitch.managers.vault_manager import VaultManager
from WorldStitch.models.user import User
from WorldStitch.storage.storage_base import StorageBackend
from WorldStitch.storage.storage_router import StorageRouter

if TYPE_CHECKING:
    from WorldStitch.ai.core.ai_base import AIInterface


class AppContext:
    """
    Central service locator — holds every service the app needs.

    Usage
    -----
    Construct once in main.py and pass to every controller/view:

        ctx = AppContext(config)
        ctx.ai = get_model_backend(config, storage=ctx.storage)

    Then inject into GUI:

        window = LoreMainApp(ctx=ctx)

    Attributes
    ----------
    config : Config
        Loaded application configuration.
    storage : StorageBackend
        Primary storage backend. All managers share this instance.
    ai : AIInterface | None
        AI engine — set by main.py after AppContext is constructed.
    current_user_id : str | None
        Active user for single-user mode. Replace with session-based
        identity when full auth is implemented.
    users : UserManager
    notes : NoteManager
    vaults : VaultManager
    groups : GroupManager
    folders : FolderManager
    characters : CharacterManager
    maps : MapManager
    permissions : PermissionChecker
    """

    def __init__(self, config: Config, storage: Optional[StorageBackend] = None):
        self.config = config

        # Migrate old DB names on first run after rebrands.
        # ward_dnd.db → worldstitch.db  (original legacy name)
        # mythos_engine.db → worldstitch.db  (MythosEngine → WorldStitch rebrand)
        _project_root = Path(config.VAULT_PATH).resolve().parent
        _db_new = _project_root / "worldstitch.db"
        if not _db_new.exists():
            import shutil

            for _db_old_name in ("mythos_engine.db", "ward_dnd.db"):
                _db_old = _project_root / _db_old_name
                if _db_old.exists():
                    shutil.copy2(str(_db_old), str(_db_new))
                    break

        # Backend is resolved via StorageRouter (respects config.VAULT_TYPE).
        # StorageRouter proxies all StorageBackend calls to its active backend,
        # so callers use ctx.storage exactly like a raw StorageBackend.
        # A custom backend may be injected via constructor — used in tests.
        self.storage: StorageBackend = storage or StorageRouter(config)

        # AI engine — wired up by main.py after construction.
        self.ai: Optional[AIInterface] = None

        # Active user — set from login dialog in main.py.
        self.current_user_id: Optional[str] = None

        # --- Managers — all share the same storage instance ---
        self.users = UserManager(self.storage)
        self.notes = NoteManager(self.storage)
        self.vaults = VaultManager(self.storage)
        self.groups = GroupManager(self.storage)
        self.folders = FolderManager(self.storage)
        self.characters = CharacterManager(self.storage)
        self.maps = MapManager(self.storage)
        self.invites = InviteManager(self.storage)

        # Permission checker — stateless, shared across all managers
        self.permissions = PermissionChecker()

        # Auth — session lifecycle + login/logout logic
        self._auth_sessions = AuthSessionManager(self.storage)
        self.auth = AuthManager(self.storage, self._auth_sessions)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @property
    def current_user(self) -> Optional[User]:
        """Return the active User object, or None if not logged in."""
        if self.current_user_id:
            return self.users.get_user(self.current_user_id)
        return None

    @property
    def is_admin(self) -> bool:
        """True if the current user has the 'admin' role."""
        user = self.current_user
        return user is not None and "admin" in user.roles

    # ------------------------------------------------------------------
    # AI helpers
    # ------------------------------------------------------------------

    @property
    def cost_tracker(self):
        """Return the CostTracker from the SQLite backend, or None if unavailable."""
        return getattr(self.storage, "cost_tracker", None)

    @property
    def analytics(self):
        """Return the AnalyticsTracker (lazy-initialised, consent-gated)."""
        if not hasattr(self, "_analytics"):
            from WorldStitch.analytics.tracker import AnalyticsTracker

            version = getattr(self.config, "VERSION", "1.0.0")
            self._analytics = AnalyticsTracker(self.storage, version)
        return self._analytics

    def has_ai(self) -> bool:
        """Return True if an AI engine has been wired up."""
        return self.ai is not None

    def require_ai(self) -> "AIInterface":
        """Return the AI engine or raise if not yet wired up."""
        if self.ai is None:
            raise RuntimeError("AI engine has not been initialised on AppContext.")
        return self.ai
