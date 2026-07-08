"""LLM provider registry and factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..base import LLMProvider

_PROVIDERS: dict[str, str] = {
    "ollama": ".ollama_provider.OllamaProvider",
    "openai": ".openai_provider.OpenAIProvider",
    "anthropic": ".anthropic_provider.AnthropicProvider",
    "vllm": ".vllm_provider.VLLMProvider",
    "lmstudio": ".lmstudio_provider.LMStudioProvider",
    "llamafile": ".llamafile_provider.LlamafileProvider",
}


def get_provider(config) -> LLMProvider:
    """Get a provider instance by name."""
    name = config.provider.lower()

    if name not in _AVAILABLE:
        # Lazy load
        _load_provider(name)

    if name not in _AVAILABLE:
        available = ", ".join(sorted(_PROVIDERS.keys()))
        raise ValueError(
            f"Unknown provider: {name}. Available: {available}\n"
            f"Install the provider or check your config."
        )

    return _AVAILABLE[name](config)


_AVAILABLE: dict[str, type] = {}


def _load_provider(name: str) -> None:
    """Lazy-load a provider module."""
    import importlib

    if name not in _PROVIDERS:
        return

    module_path, class_name = _PROVIDERS[name].rsplit(".", 1)
    try:
        module = importlib.import_module(module_path, package="forge.llm.providers")
        cls = getattr(module, class_name)
        _AVAILABLE[name] = cls
    except ImportError as e:
        raise ImportError(
            f"Provider '{name}' requires additional dependencies: {e}\n"
            f"Install with: pip install forge-coding[{name}]"
        ) from e
