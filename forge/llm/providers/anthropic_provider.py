"""
Anthropic Claude provider — for users who want cloud Claude as a backend.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

import httpx

from ..base import LLMMessage, LLMProvider, LLMResponse, StreamChunk, ToolDefinition


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    API_BASE = "https://api.anthropic.com"

    def __init__(self, config):
        super().__init__(config)
        self.model = config.model or "claude-sonnet-4-20250514"
        self.api_key = config.api_key

        if not self.api_key:
            raise ValueError("Anthropic requires an API key. Set FORGE_API_KEY or api_key in config.")

        self._client = httpx.AsyncClient(
            base_url=self.API_BASE,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=httpx.Timeout(300.0, connect=10.0),
        )

    def _convert_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[str, list[dict]]:
        """Convert to Anthropic format (system separate, no system role in messages)."""
        system = ""
        converted = []

        for msg in messages:
            if msg.role == "system":
                system += msg.content + "\n"
            elif msg.role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    func = tc.get("function", {})
                    content.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}")),
                    })
                converted.append({"role": "assistant", "content": content})
            else:
                converted.append({"role": msg.role, "content": msg.content})

        return system.strip(), converted

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[ToolDefinition]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> LLMResponse:
        start = time.monotonic()
        system, msgs = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        resp = await self._client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        elapsed = time.monotonic() - start

        content = ""
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"]),
                    },
                })

        usage = data.get("usage", {})
        result = LLMResponse(
            content=content,
            tool_calls=tool_calls or None,
            finish_reason=data.get("stop_reason"),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
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
        system, msgs = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": msgs,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        async with self._client.stream("POST", "/v1/messages", json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                line = line[6:]
                if line == "[DONE]":
                    yield StreamChunk(done=True)
                    break

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", "")
                if event_type == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield StreamChunk(delta=delta.get("text", ""))
                    elif delta.get("type") == "input_json_delta":
                        yield StreamChunk(
                            tool_calls=[{"function": {"arguments": delta.get("partial_json", "")}}]
                        )
                elif event_type == "message_stop":
                    yield StreamChunk(done=True, finish_reason="stop")

    async def available_models(self) -> list[str]:
        return [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-haiku-20241022",
        ]

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/v1/models", timeout=5.0)
            return resp.status_code in (200, 401)
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
