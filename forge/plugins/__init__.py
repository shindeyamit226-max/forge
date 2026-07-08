"""
Plugin System — extensible architecture for Forge.
Plugins can: add tools, add parsers, add generators, hook into events.
"""

from .loader import PluginLoader, Plugin
from .hooks import HookRegistry, Hook

__all__ = ["PluginLoader", "Plugin", "HookRegistry", "Hook"]
