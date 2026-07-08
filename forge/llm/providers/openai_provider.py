"""
OpenAI-compatible provider — works with OpenAI, vLLM, LM Studio, LiteLLM, etc.
Any API that follows the OpenAI chat completions format.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

import httpx

from ..base import LLMMessage, LLMProvider, LLMResponse, StreamChunk, ToolDefinition


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider."""

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config.api_base.rstrip("/")
        self.model = config.model
        self.api_key = config.api_key or "no-key"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
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
        start = time.monotonic()

        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": False,
        }

        if tools:
            payload["tools"] = [t.to_dict() for t in tools]
            payload["tool_choice"] = "auto"

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        elapsed = time.monotonic() - start
        choice = data["choices"][0]
        message = choice["message"]

        result = LLMResponse(
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls"),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage"),
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
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "top_p": self.config.top_p,
            "stream": True,
        }

        if tools:
            payload["tools"] = [t.to_dict() for t in tools]
            payload["tool_choice"] = "auto"

        async with self._client.stream(
            "POST", "/chat/completions", json=payload
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line == "data: [DONE]":
                    if line == "data: [DONE]":
                        yield StreamChunk(done=True)
                    continue

                if line.startswith("data: "):
                    line = line[6:]

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                delta = data["choices"][0].get("delta", {})
                finish = data["choices"][0].get("finish_reason")

                yield StreamChunk(
                    delta=delta.get("content") or "",
                    tool_calls=delta.get("tool_calls"),
                    finish_reason=finish,
                    done=finish is not None,
                )

    async def available_models(self) -> list[str]:
        try:
            resp = await self._client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return [self.model]

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
