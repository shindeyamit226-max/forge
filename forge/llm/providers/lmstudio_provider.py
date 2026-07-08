"""LM Studio provider — GUI-based local model serving."""
from .openai_provider import OpenAIProvider


class LMStudioProvider(OpenAIProvider):
    """LM Studio uses OpenAI-compatible API at localhost:1234."""
    pass
