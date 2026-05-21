"""
Shared pytest fixtures for WorldStitch tests.

Fixtures are designed to work without a real vault, GUI, or API key.
All storage is in-memory or in a tmp directory.
"""

import pytest

from WorldStitch.config.config import Config

# ---------------------------------------------------------------------------
# Config fixture — provides a real Config object with safe test defaults
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def config(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("vault")
    cfg = Config.__new__(Config)
    cfg._data = {
        "VAULT_PATH": str(tmp),
        "VAULT_TYPE": "hybrid",
        "CORE_DATA_PATH": str(tmp / "data"),
        "OPENAI_API_KEY": "test-key",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "COMPLETION_MODEL": "gpt-4o",
        "MAX_TOKENS": 4000,
        "LOG_FILE": str(tmp / "test.log"),
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
    }
    cfg._path = tmp / "settings.json"
    import logging

    cfg.logger = logging.getLogger("test")
    return cfg


# ---------------------------------------------------------------------------
# Storage fixture — real HybridStorage in a temp directory
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def storage(tmp_path_factory):
    from WorldStitch.storage.hybrid_storage import HybridStorage

    tmp = tmp_path_factory.mktemp("storage")
    return HybridStorage(str(tmp))


# ---------------------------------------------------------------------------
# AI fixture — mock AI engine that returns predictable responses
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ai():
    from unittest.mock import MagicMock

    mock_ai = MagicMock()
    mock_ai.ask.return_value = ("Mock response", 10, 5)
    mock_ai.summarize.return_value = ("Mock summary", 10, 5)
    mock_ai.suggest_tags.return_value = ("tag1, tag2", 10, 5)
    mock_ai.propose_links.return_value = ("[[Note A]]", 10, 5)
    return mock_ai
