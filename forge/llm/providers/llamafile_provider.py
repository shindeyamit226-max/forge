"""Llamafile provider — single-file local LLM execution."""
from .openai_provider import OpenAIProvider


class LlamafileProvider(OpenAIProvider):
    """Llamafile uses OpenAI-compatible API at localhost:8080."""
    pass
