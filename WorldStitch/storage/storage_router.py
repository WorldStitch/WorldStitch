# WorldStitch/storage/storage_router.py
"""
StorageRouter — dynamically loads the storage backend specified in config.

``VAULT_TYPE`` in settings.json controls which backend is instantiated:
  - ``"sqlite"``   →  SQLiteBackend(db_path, vault_path)   [default]
  - ``"hybrid"``   →  HybridStorage(vault_path)
  - ``"obsidian"`` →  ObsidianStorage(vault_path)
  - Any other type whose module follows the pattern
    ``WorldStitch.storage.<type>_storage.<Type>Storage``

The router proxies all attribute access to the active backend, so callers
can use it as a drop-in replacement for any StorageBackend.
"""

import importlib
from pathlib import Path

from WorldStitch.storage.storage_base import StorageBackend


class StorageRouter:
    def __init__(self, config):
        self._config = config
        self.backend = self._load_backend()

    def _load_backend(self) -> StorageBackend:
        storage_type = getattr(self._config, "VAULT_TYPE", "sqlite").lower()
        vault_path = getattr(self._config, "VAULT_PATH", None)
        if not vault_path:
            raise ValueError("VAULT_PATH must be set in config.")

        # Map type → (module_suffix, class_name) for backends that don't follow
        # the default "{type}_storage" / "{Type}Storage" naming convention.
        _overrides = {
            "sqlite": ("sqlite_backend", "SQLiteBackend"),
        }
        if storage_type in _overrides:
            module_suffix, cls_name = _overrides[storage_type]
        else:
            module_suffix = f"{storage_type}_storage"
            cls_name = f"{storage_type.capitalize()}Storage"
        module_name = f"WorldStitch.storage.{module_suffix}"

        try:
            module = importlib.import_module(module_name)
            backend_cls = getattr(module, cls_name)

            # SQLite needs both db_path and vault_path
            if storage_type == "sqlite":
                db_path = str(Path(vault_path).resolve().parent / "worldstitch.db")
                instance = backend_cls(db_path=db_path, vault_path=vault_path)
            else:
                instance = backend_cls(vault_path)

            if not isinstance(instance, StorageBackend):
                raise TypeError(f"{cls_name} does not implement StorageBackend")
            return instance
        except (ModuleNotFoundError, AttributeError, TypeError) as e:
            raise ImportError(
                f"Could not load storage backend '{storage_type}': {e}\n"
                "Valid VAULT_TYPE values: sqlite, hybrid, obsidian"
            )

    def reload_backend(self, config=None):
        if config is not None:
            self._config = config
        self.backend = self._load_backend()

    def __getattr__(self, name):
        return getattr(self.backend, name)


def get_storage_backend(config):
    """
    Returns the actual storage backend instance based on config.
    Use this to get a raw backend if you don't want a router wrapper.
    """
    return StorageRouter(config).backend
