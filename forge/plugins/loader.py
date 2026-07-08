"""
Plugin Loader — discover, load, and manage plugins.
Plugins are Python files in ~/.forge/plugins/ or .forge/plugins/.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class Plugin:
    """A loaded plugin."""
    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    path: str = ""
    tools: list[str] = field(default_factory=list)
    parsers: list[str] = field(default_factory=list)
    generators: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict = field(default_factory=dict)


class PluginLoader:
    """Discover and load Forge plugins."""

    def __init__(self, plugin_dirs: list[str] = None):
        self.plugin_dirs = plugin_dirs or [
            str(Path.home() / ".forge" / "plugins"),
            ".forge/plugins",
        ]
        self.plugins: dict[str, Plugin] = {}
        self._loaded_modules: dict[str, Any] = {}

    def discover(self) -> list[str]:
        """Discover available plugins."""
        discovered = []
        for plugin_dir in self.plugin_dirs:
            path = Path(plugin_dir)
            if not path.exists():
                continue

            for item in path.iterdir():
                if item.is_dir() and (item / "__init__.py").exists():
                    discovered.append(str(item))
                elif item.suffix == ".py" and not item.name.startswith("_"):
                    discovered.append(str(item))

        return discovered

    def load(self, plugin_path: str) -> Optional[Plugin]:
        """Load a single plugin."""
        path = Path(plugin_path)

        if path.is_dir():
            module_name = f"forge_plugin_{path.name}"
            spec = importlib.util.spec_from_file_location(
                module_name, path / "__init__.py",
                submodule_search_locations=[str(path)],
            )
        else:
            module_name = f"forge_plugin_{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, path)

        if not spec or not spec.loader:
            return None

        try:
            module = importlib.util.module_from_spec(spec)
            module.__plugin__ = True
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Extract plugin metadata
            plugin = Plugin(
                name=getattr(module, "__plugin_name__", path.stem),
                version=getattr(module, "__plugin_version__", "0.0.0"),
                description=getattr(module, "__plugin_description__", ""),
                author=getattr(module, "__plugin_author__", ""),
                path=str(path),
            )

            # Register tools if present
            if hasattr(module, "register_tools"):
                module.register_tools()
                plugin.tools = getattr(module, "_registered_tools", [])

            # Register hooks if present
            if hasattr(module, "register_hooks"):
                module.register_hooks()

            self.plugins[plugin.name] = plugin
            self._loaded_modules[plugin.name] = module
            return plugin

        except Exception as e:
            print(f"Warning: Failed to load plugin {path.name}: {e}", file=sys.stderr)
            return None

    def load_all(self) -> list[Plugin]:
        """Discover and load all plugins."""
        loaded = []
        for path in self.discover():
            plugin = self.load(path)
            if plugin:
                loaded.append(plugin)
        return loaded

    def unload(self, name: str) -> bool:
        """Unload a plugin."""
        if name in self.plugins:
            self.plugins[name].enabled = False
            module = self._loaded_modules.pop(name, None)
            if module:
                # Clean up
                if hasattr(module, "cleanup"):
                    module.cleanup()
            return True
        return False

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self.plugins.get(name)

    def list_plugins(self) -> list[Plugin]:
        return list(self.plugins.values())

    def reload(self, name: str) -> Optional[Plugin]:
        """Reload a plugin."""
        plugin = self.plugins.get(name)
        if plugin:
            self.unload(name)
            return self.load(plugin.path)
        return None
