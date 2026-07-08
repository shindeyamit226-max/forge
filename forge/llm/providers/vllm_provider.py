"""vLLM provider — high-performance local inference."""
from .openai_provider import OpenAIProvider


class VLLMProvider(OpenAIProvider):
    """vLLM uses OpenAI-compatible API format."""
    pass
