"""
LLM Provider base — abstract interface for all LLM backends.
Supports streaming, tool calls, and structured output.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Protocol


@dataclass
class LLMMessage:
    """A message in the conversation."""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    tool_calls: Optional[list[dict]] = None
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    model: Optional[str] = None
    latency_ms: float = 0.0

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def token_count(self) -> int:
        if self.usage:
            return self.usage.get("total_tokens", 0)
        return 0


@dataclass
class StreamChunk:
    """A chunk from a streaming response."""
    delta: str = ""
    tool_calls: Optional[list[dict]] = None
    finish_reason: Optional[str] = None
    done: bool = False


@dataclass
class ToolDefinition:
    """Definition of a tool for the LLM."""
    name: str
    description: str
    parameters: dict  # JSON Schema

    def to_dict(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, config):
        self.config = config
        self._request_count = 0
        self._total_tokens = 0
        self._total_latency = 0.0

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> LLMResponse:
        """Send a chat completion request."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response."""
        ...

    @abstractmethod
    async def available_models(self) -> list[str]:
        """List available models from the provider."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is reachable."""
        ...

    def record_usage(self, response: LLMResponse, latency: float) -> None:
        """Track usage statistics."""
        self._request_count += 1
        self._total_latency += latency
        if response.usage:
            self._total_tokens += response.usage.get("total_tokens", 0)

    @property
    def stats(self) -> dict:
        return {
            "requests": self._request_count,
            "total_tokens": self._total_tokens,
            "total_latency_s": round(self._total_latency, 2),
            "avg_latency_ms": round(
                (self._total_latency / max(self._request_count, 1)) * 1000, 1
            ),
        }
