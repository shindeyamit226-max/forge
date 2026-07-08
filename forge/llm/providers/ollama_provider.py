"""
Ollama provider — runs 100% locally, zero cloud dependency.
Supports all Ollama models: CodeLlama, DeepSeek Coder, Llama 3, Mistral, etc.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

import httpx

from ..base import LLMMessage, LLMProvider, LLMResponse, StreamChunk, ToolDefinition


class OllamaProvider(LLMProvider):
    """Ollama LLM provider — local inference."""

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config.api_base.rstrip("/v1").rstrip("/")
        self.model = config.model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(300.0, connect=10.0),
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> LLMResponse:
        """Send chat request to Ollama."""
        start = time.monotonic()

        # Build Ollama-format request
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
                "top_p": self.config.top_p,
            },
        }

        # Add tools if supported
        if tools:
            payload["tools"] = [t.to_dict() for t in tools]

        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        elapsed = time.monotonic() - start
        msg = data.get("message", {})

        result = LLMResponse(
            content=msg.get("content", ""),
            tool_calls=msg.get("tools") if msg.get("tools") else None,
            finish_reason="stop" if data.get("done") else "length",
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
            model=data.get("model", self.model),
            latency_ms=elapsed * 1000,
        )
        self.record_usage(result, elapsed)
        return result

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat response from Ollama."""
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature or self.config.temperature,
                "num_predict": max_tokens or self.config.max_tokens,
                "top_p": self.config.top_p,
            },
        }

        if tools:
            payload["tools"] = [t.to_dict() for t in tools]

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            buffer = ""

            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    buffer += line
                    continue

                msg = data.get("message", {})
                done = data.get("done", False)

                yield StreamChunk(
                    delta=msg.get("content", ""),
                    tool_calls=msg.get("tools") if msg.get("tools") else None,
                    finish_reason="stop" if done else None,
                    done=done,
                )

                if done:
                    break

    async def available_models(self) -> list[str]:
        """List models available in Ollama."""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return [self.model]

    async def health_check(self) -> bool:
        """Check if Ollama is running."""
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
