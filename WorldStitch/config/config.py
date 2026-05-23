import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

CONFIG_FILENAME = "settings.json"
DEFAULT_CONFIG = {
    "VAULT_PATH": "./Obsidian",
    "VAULT_TYPE": "sqlite",
    "CORE_DATA_PATH": "./WorldStitch/data",
    "OPENAI_API_KEY": "",
    "EMBEDDING_MODEL": "text-embedding-3-small",
    "COMPLETION_MODEL": "gpt-4o",
    "MAX_TOKENS": 4000,
    "LOG_FILE": "logs/app.log",
    "LOG_LEVEL": "INFO",
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


class Config:
    def __init__(self):
        self._path = Path(__file__).parent / "settings.json"
        self._data = DEFAULT_CONFIG.copy()
        self._load()
        self._init_logger()

    def _load(self):
        # Load .env files from project root (two levels up from this file).
        # Load order (later files override earlier ones):
        #   1. .env                  - shared secrets, never committed
        #   2. .env.{APP_ENV}        - environment-specific overrides
        #
        # Set APP_ENV=production or APP_ENV=test to switch modes.
        # Default is "development".
        try:
            from dotenv import load_dotenv

            _root = Path(__file__).resolve().parent.parent.parent
            _env_file = _root / ".env"
            if _env_file.exists():
                load_dotenv(_env_file)
            _app_env = os.getenv("APP_ENV", "development").lower()
            _env_override = _root / f".env.{_app_env}"
            if _env_override.exists():
                load_dotenv(_env_override, override=True)
        except (ImportError, OSError, Exception):
            pass

        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._data.clear()
                for key in DEFAULT_CONFIG:
                    val = raw.get(key, DEFAULT_CONFIG[key])
                    env_val = os.getenv(key)
                    # Only use env var if it's non-empty — a blank .env line
                    # like "OPENAI_API_KEY=" should NOT override settings.json.
                    if env_val is not None and env_val != "":
                        val = self._cast_value(env_val, DEFAULT_CONFIG[key])
                    self._data[key] = val
            except Exception as e:
                print(f"[config] Failed to load or parse config file: {e}")
                self._data = DEFAULT_CONFIG.copy()
        else:
            self._data = DEFAULT_CONFIG.copy()

    def _cast_value(self, val: str, default: Any) -> Any:
        if isinstance(default, bool):
            return val.lower() in ("1", "true", "yes")
        if isinstance(default, int):
            return int(val)
        return val

    def save(self):
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            self.log_info("Settings saved.")
        except Exception as e:
            self.log_error(f"Failed to save config: {e}")

    def _init_logger(self):
        self.logger = logging.getLogger("MythosLogger")
        self.logger.setLevel(logging.DEBUG)

        log_file = self._data.get("LOG_FILE", "logs/app.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        fh.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(message)s"))
        ch.setLevel(logging.INFO)

        self.logger.handlers.clear()
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

    def log_info(self, msg):
        self.logger.info(msg)

    def log_warn(self, msg):
        self.logger.warning(msg)

    def log_error(self, msg):
        self.logger.error(msg)

    def reload(self):
        self._load()
        self._init_logger()

    def __getattr__(self, name):
        if name in self._data:
            return self._data[name]
        raise AttributeError(f"Config has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name in ("_path", "_data", "logger"):
            super().__setattr__(name, value)
        elif name in DEFAULT_CONFIG:
            self._data[name] = value
            self.save()
        else:
            raise AttributeError(f"Cannot set unknown config field '{name}'")

    def get(self, key, default=None):
        return self._data.get(key, default)

    @property
    def API_KEY_ENCRYPTION_SECRET(self) -> Optional[str]:
        """Env-only secret for Fernet encryption of user API keys.  Never stored in settings.json."""
        return os.environ.get("API_KEY_ENCRYPTION_SECRET") or None


def log_exception(e: Exception, context: str = ""):
    logger = logging.getLogger("MythosLogger")
    if context:
        logger.exception("%s — unhandled exception: %s", context, e)
    else:
        logger.exception("Unhandled exception: %s", e)


def load_note_templates():
    """
    Loads and merges built-in and user note templates.
    Returns: dict of {template_name: {"description": str, "content": str}}
    """
    import yaml

    builtins = {
        "Blank Note": {"description": "Empty note", "content": "# Title\n\n"},
        "NPC": {
            "description": "D&D non-player character",
            "content": "# NPC Name\n\n## Appearance\n\n## Personality\n\n## Background\n",
        },
        "Place": {
            "description": "Location/setting",
            "content": "# Place Name\n\n## Description\n\n## Secrets\n",
        },
        "Item": {
            "description": "Magic item",
            "content": "# Item Name\n\n## Description\n\n## Abilities\n",
        },
    }

    config_dir = Path(__file__).parent
    user_templates_path = config_dir / "note_templates.yaml"
    user_templates = {}
    if user_templates_path.exists():
        try:
            with user_templates_path.open("r", encoding="utf-8") as f:
                user_templates = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Could not load note_templates.yaml: {e}")

    templates = builtins.copy()
    for k, v in (user_templates or {}).items():
        templates[k] = v
    return templates
