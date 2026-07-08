"""
Forge configuration — layered, validated, with sane defaults.
Priority: CLI flags > env vars > project config > user config > defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULTS = {
    "provider": "ollama",
    "model": "codellama:13b",
    "temperature": 0.1,
    "top_p": 0.95,
    "max_tokens": 4096,
    "max_iterations": 30,
    "max_context_tokens": 32000,
    "auto_approve": False,
    "theme": "forge_dark",
    "api_base": "http://localhost:11434/v1",
    "api_key": None,
    "confirm_destructive": True,
    "sandbox_shell": False,
    "watch_files": True,
    "git_auto_commit": False,
    "log_level": "INFO",
    "history_file": "~/.forge/history.json",
    "snippets_dir": "~/.forge/snippets",
    "custom_tools_dir": "~/.forge/tools",
}

FORGE_HOME = Path.home() / ".forge"
PROJECT_CONFIG = Path(".forge.yaml")


@dataclass
class Config:
    """Forge configuration with layered precedence."""

    # LLM settings
    provider: str = "ollama"
    model: str = "codellama:13b"
    temperature: float = 0.1
    top_p: float = 0.95
    max_tokens: int = 4096
    api_base: str = "http://localhost:11434/v1"
    api_key: Optional[str] = None

    # Agent settings
    max_iterations: int = 30
    max_context_tokens: int = 32000
    auto_approve: bool = False

    # Safety
    confirm_destructive: bool = True
    sandbox_shell: bool = False

    # UI
    theme: str = "forge_dark"

    # Features
    watch_files: bool = True
    git_auto_commit: bool = False

    # Paths
    history_file: str = "~/.forge/history.json"
    snippets_dir: str = "~/.forge/snippets"
    custom_tools_dir: str = "~/.forge/tools"
    log_level: str = "INFO"

    # Runtime overrides
    _overrides: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> Config:
        """Load config from layered sources."""
        data: dict[str, Any] = dict(DEFAULTS)

        # Layer 1: User config (~/.forge/config.yaml)
        user_config = FORGE_HOME / "config.yaml"
        if user_config.exists():
            data.update(cls._load_yaml(user_config))

        # Layer 2: Project config (.forge.yaml)
        if PROJECT_CONFIG.exists():
            data.update(cls._load_yaml(PROJECT_CONFIG))

        # Layer 3: Explicit config file
        if config_path and config_path.exists():
            data.update(cls._load_yaml(config_path))

        # Layer 4: Environment variables (FORGE_*)
        env_map = {
            "FORGE_PROVIDER": ("provider", str),
            "FORGE_MODEL": ("model", str),
            "FORGE_API_BASE": ("api_base", str),
            "FORGE_API_KEY": ("api_key", str),
            "FORGE_TEMPERATURE": ("temperature", float),
            "FORGE_MAX_TOKENS": ("max_tokens", int),
            "FORGE_MAX_ITERATIONS": ("max_iterations", int),
            "FORGE_AUTO_APPROVE": ("auto_approve", cls._parse_bool),
            "FORGE_THEME": ("theme", str),
            "FORGE_LOG_LEVEL": ("log_level", str),
            "FORGE_SANDBOX_SHELL": ("sandbox_shell", cls._parse_bool),
        }
        for env_var, (key, converter) in env_map.items():
            val = os.environ.get(env_var)
            if val is not None:
                try:
                    data[key] = converter(val)
                except (ValueError, TypeError):
                    pass

        # Filter to known fields
        known = {f.name for f in cls.__dataclass_fields__.values() if f.name != "_overrides"}
        filtered = {k: v for k, v in data.items() if k in known}

        return cls(**filtered)

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    @staticmethod
    def _parse_bool(val: str) -> bool:
        return val.lower() in ("true", "1", "yes", "on")

    def get(self, key: str, default: Any = None) -> Any:
        return self._overrides.get(key, getattr(self, key, default))

    def override(self, key: str, value: Any) -> None:
        self._overrides[key] = value

    def ensure_dirs(self) -> None:
        """Create required directories."""
        FORGE_HOME.mkdir(parents=True, exist_ok=True)
        Path(self.snippets_dir).expanduser().mkdir(parents=True, exist_ok=True)
        Path(self.custom_tools_dir).expanduser().mkdir(parents=True, exist_ok=True)
