# WorldStitch/ai/registry.py

from typing import Dict, Type

from WorldStitch.ai.core.ai_base import AIInterface

# Global mapping: capability name -> AIInterface subclass
_PLUGINS: Dict[str, Type[AIInterface]] = {}


def register_plugin(name: str):
    """Decorator to register an AIInterface implementation under a capability name."""

    def decorator(cls: Type[AIInterface]):
        if not issubclass(cls, AIInterface):
            raise TypeError(f"{cls.__name__} must implement AIInterface")
        _PLUGINS[name] = cls
        return cls

    return decorator


def get_plugin(name: str) -> Type[AIInterface]:
    """Retrieve the plugin class for a given capability."""
    try:
        return _PLUGINS[name]
    except KeyError:
        raise ImportError(f"No AI plugin registered under name '{name}'")


def list_plugins() -> Dict[str, Type[AIInterface]]:
    """Return the full mapping of capability names -> plugin classes."""
    return dict(_PLUGINS)


# Force import of core plugin modules so they register themselves
# This avoids circular imports and ensures @register_plugin decorators run
from WorldStitch.ai.core import loreai_engine as _loreai_engine  # noqa: F401
from WorldStitch.ai.core import openai_engine as _openai_engine  # noqa: F401
