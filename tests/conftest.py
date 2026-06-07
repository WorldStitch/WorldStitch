"""
Shared pytest fixtures for WorldStitch server integration tests.

Strategy
--------
The production app uses SQLiteBackend which requires a real PostgreSQL
DATABASE_URL.  For CI-friendly tests we use HybridStorage (file-backed,
zero config).  HybridStorage has two gaps patched by TestHybridStorage:

  1. _save_global uses plain json.dumps, which can't handle the datetime
     objects that CoreModel.created_at / last_modified default to.
     We override _save_global with a datetime-aware encoder.

  2. list_vaults is absent — vault routes call storage.list_vaults() to
     enumerate accessible vaults.  We add it by scanning .ws_meta/vaults/.

The FastAPI lifespan creates its own AppContext at startup.  We bypass it
entirely by registering a dependency override for `get_ctx` before the
TestClient starts — every route that calls `Depends(get_ctx)` gets our
isolated test context instead.

The env-var block at the top of this file is evaluated at import time
(before `from server.app import app`), which keeps the lifespan from
crashing when it runs inside TestClient.__enter__.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Env-var guard — must be set BEFORE server.app is imported so the
# lifespan's Config() + StorageRouter() picks up hybrid (no DATABASE_URL).
# ---------------------------------------------------------------------------
_LIFESPAN_TMP = tempfile.mkdtemp(prefix="ws_lifespan_")
os.environ.setdefault("VAULT_TYPE", "hybrid")
os.environ.setdefault("VAULT_PATH", _LIFESPAN_TMP)
os.environ.setdefault("LOG_FILE", os.path.join(_LIFESPAN_TMP, "test.log"))

import pytest
from fastapi.testclient import TestClient

from server.app import app
from server.auth_utils import create_jwt
from server.deps import get_ctx
from WorldStitch.config.config import Config
from WorldStitch.context.app_context import AppContext
from WorldStitch.models.vault import Vault
from WorldStitch.storage.hybrid_storage import HybridStorage

# ---------------------------------------------------------------------------
# TestHybridStorage — two fixes on top of HybridStorage
# ---------------------------------------------------------------------------


def _json_default(obj):
    """JSON encoder that converts datetime/date to ISO strings."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class TestHybridStorage(HybridStorage):
    """HybridStorage with two patches required for headless testing.

    Problem: HybridStorage's save_* methods call json.dumps(model.model_dump())
    which breaks on CoreModel's datetime fields (created_at / last_modified).
    Fix: use json.loads(model.model_dump_json()) which pydantic serialises safely.

    Problem: list_vaults is absent; vault routes call storage.list_vaults() via
    vault_access._storage_list_vaults() to enumerate accessible vaults.
    Fix: scan the .dnd_meta/vaults/ directory the storage backend writes to.
    """

    @staticmethod
    def _safe_model_json(model, indent: int = 2) -> str:
        """Serialise a pydantic model to indented JSON, datetime-safe."""
        return json.dumps(json.loads(model.model_dump_json()), indent=indent)

    # Fix 1a: _save_global (users, groups) — used by save_user / save_group
    def _save_global(self, model: str, data: dict) -> None:
        path = self._global_path(model)
        path.write_text(json.dumps(data, indent=2, default=_json_default), encoding="utf-8")

    # Fix 1b: save_vault — datetime in CoreModel.created_at / last_modified
    def save_vault(self, vault: Vault) -> None:
        path = self._dnd_meta_path("vaults", vault.id)
        path.write_text(self._safe_model_json(vault), encoding="utf-8")

    # Fix 1c: save_invite — datetime in InviteCode.expires_at
    def save_invite(self, invite) -> None:
        path = self._dnd_meta_path("invites", invite.id)
        path.write_text(self._safe_model_json(invite), encoding="utf-8")

    # Fix 2: list_vaults — absent from HybridStorage; scans .dnd_meta/vaults/
    #
    # IMPORTANT: SQLiteBackend scopes its vault query by the current user
    # context (set via set_user_context before listing).  Returning every
    # vault unconditionally causes _first_owned_or_member's fallback path
    # to hand unrelated vaults to new users, defeating access-control tests.
    # We replicate SQLiteBackend's user-scoping by filtering on owner_id and
    # members — admins see all vaults, regular users only see their own.
    def list_vaults(self) -> list[Vault]:
        meta_dir = self._dnd_meta_dir("vaults")
        current_uid: str | None = getattr(self, "_current_user_id", None)
        is_admin: bool = getattr(self, "_is_admin", False)
        vaults: list[Vault] = []
        for path in meta_dir.glob("*.json"):
            try:
                vault = Vault.model_validate(json.loads(path.read_text(encoding="utf-8")))
                if (
                    is_admin
                    or current_uid is None
                    or vault.owner_id == current_uid
                    or current_uid in (vault.members or [])
                ):
                    vaults.append(vault)
            except Exception:
                pass
        return vaults


# ---------------------------------------------------------------------------
# Isolated AppContext using TestHybridStorage
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_ctx(tmp_path_factory):
    """A fresh AppContext backed by file storage in a temp directory."""
    vault_tmp = tmp_path_factory.mktemp("vault")
    global_tmp = tmp_path_factory.mktemp("global")  # keeps test users off ~/.worldstitch_ai/

    cfg = Config.__new__(Config)
    cfg._data = {
        "VAULT_PATH": str(vault_tmp),
        "VAULT_TYPE": "hybrid",
        "CORE_DATA_PATH": str(vault_tmp / "data"),
        "OPENAI_API_KEY": "",  # deliberately empty → /ai/ask returns 403
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "COMPLETION_MODEL": "gpt-4o",
        "MAX_TOKENS": 4000,
        "LOG_FILE": str(vault_tmp / "test.log"),
        "LOG_LEVEL": "DEBUG",
        "AUTO_REFRESH_INTERVAL": 300,
        "ENABLE_EXPERIMENTAL": False,
        "AI_BACKENDS": {
            "ask": "openai",
            "summarize": "openai",
            "suggest_tags": "openai",
            "propose_links": "openai",
            "search_context": "loreai",
        },
        "THEME": "Light",
        "FONT_SIZE": "Medium",
        "SHOW_TOOLTIPS": True,
        "STARTUP_TAB": "Dashboard",
        "COMPACT_MODE": False,
        "APP_NAME": "WorldStitch",
        "PREFERRED_MODEL": "",
        "STREAMING_ENABLED": True,
        "AI_HISTORY_LIMIT": 10,
    }
    cfg._path = vault_tmp / "settings.json"
    cfg.logger = logging.getLogger("test")

    storage = TestHybridStorage(str(vault_tmp), global_data_path=str(global_tmp))
    return AppContext(cfg, storage=storage)


# ---------------------------------------------------------------------------
# TestClient — dependency override injects test_ctx into every route
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client(test_ctx):
    """Sync TestClient with get_ctx overridden to use the isolated context."""
    app.dependency_overrides[get_ctx] = lambda: test_ctx
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# A regular user that exists for the whole test session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_user(test_ctx):
    """Create and return a persistent test user."""
    user = test_ctx.users.create_user(
        email="testuser@example.com",
        username="testuser",
        password="TestPass1!",
        roles=["user"],
    )
    # system_role defaults to "user" in the User model; set explicitly for clarity
    user.system_role = "user"
    test_ctx.users.update_user(user)
    return user


# ---------------------------------------------------------------------------
# Auth headers (valid Bearer token for test_user)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def auth_headers(test_user):
    """Authorization header dict for test_user."""
    token = create_jwt(test_user.id, test_user.email, role="member")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# A vault owned by test_user
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_vault(test_ctx, test_user):
    """Create and return a vault owned by test_user."""
    return test_ctx.vaults.create_vault(
        name="Test Vault",
        owner_id=test_user.id,
        description="Integration test vault",
    )
