"""
PyInstaller entry point for the WorldStitch FastAPI server.

Build with: scripts\build-backend.bat
The resulting dist\server\ directory is bundled into the Electron installer
as an extraResource and launched by electron/main.cjs at runtime.
"""

import os
import sys
from pathlib import Path

# ── Frozen (packaged) setup ───────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Electron passes the user-data directory so all relative paths
    # (vault, logs, DB, settings.json) resolve to a writable location
    # instead of the read-only Program Files install directory.
    _data_dir_str = os.environ.get("MYTHOS_DATA_DIR")
    if _data_dir_str:
        _data_dir = Path(_data_dir_str)
        _data_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(str(_data_dir))

        # Redirect Config._path to the user-data dir so settings persist
        # across launches.  Must happen before any Config() is instantiated.
        from WorldStitch.config import config as _cfg_module

        _settings_path = _data_dir / "config" / "settings.json"
        _settings_path.parent.mkdir(parents=True, exist_ok=True)

        def _patched_config_init(self):
            self._path = _settings_path
            self._data = _cfg_module.DEFAULT_CONFIG.copy()
            self._load()
            self._init_logger()

        _cfg_module.Config.__init__ = _patched_config_init

# ── Server startup ────────────────────────────────────────────────────────────
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("server.app:app", host="127.0.0.1", port=8741)
