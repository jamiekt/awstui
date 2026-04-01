"""AWS service plugins — auto-discovered on import."""

from __future__ import annotations

import importlib
import pkgutil

from awstui.plugin import PluginRegistry

registry = PluginRegistry()


def discover_plugins() -> PluginRegistry:
    """Import all modules in this package and register any that expose a `plugin` variable."""
    package = importlib.import_module(__name__)
    for _importer, module_name, _ispkg in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{__name__}.{module_name}")
        if hasattr(module, "plugin"):
            registry.register(module.plugin)
    return registry
