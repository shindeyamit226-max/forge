"""
Plugin system — load custom tools from user directories.
Drop a .py file in ~/.forge/tools/ and it auto-registers.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Optional

from .tools.registry import registry


def load_plugins(tools_dir: Optional[str] = None) -> list[str]:
    """
    Load custom tool plugins from a directory.

    Each .py file in the directory is loaded as a module.
    The file can use @tool decorator to register tools.

    Returns list of loaded plugin names.
    """
    if not tools_dir:
        tools_dir = str(Path.home() / ".forge" / "tools")

    tools_path = Path(tools_dir).expanduser()
    if not tools_path.exists():
        return []

    loaded = []
    for py_file in sorted(tools_path.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"forge_custom_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                # Make forge tools available in the plugin's namespace
                module.tool = registry.register
                module.registry = registry
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                loaded.append(py_file.stem)
        except Exception as e:
            print(f"Warning: Failed to load plugin {py_file.name}: {e}", file=sys.stderr)

    return loaded
