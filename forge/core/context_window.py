"""
Context Window Manager — intelligent token budget management.
Handles context truncation, summarization, and priority-based inclusion.
This is critical for working with large codebases within LLM limits.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContextItem:
    """An item in the context window with priority and token count."""
    id: str
    content: str
    tokens: int
    priority: float  # Higher = more important
    kind: str  # system, message, tool_result, file, code, plan
    can_summarize: bool = True
    can_drop: bool = False

    def __lt__(self, other):
        return self.priority < other.priority


class ContextWindowManager:
    """
    Manages the context window to stay within token limits.

    Strategy:
    1. System prompt and recent messages are always kept
    2. Tool results are truncated/dropped by priority
    3. Old messages are summarized when needed
    4. File contents are kept if recently referenced
    """

    def __init__(self, max_tokens: int = 32000, reserve_tokens: int = 4000):
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens  # Reserve for response
        self.available_tokens = max_tokens - reserve_tokens
        self.items: list[ContextItem] = []
        self._token_count = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count (rough: ~4 chars per token for English/code)."""
        # More accurate for code: count words + symbols
        words = len(re.findall(r'\w+', text))
        symbols = len(re.findall(r'[^\w\s]', text))
        return max(1, int(words * 1.3 + symbols * 0.5))

    def add(
        self,
        id: str,
        content: str,
        priority: float = 0.5,
        kind: str = "message",
        can_summarize: bool = True,
        can_drop: bool = False,
    ) -> bool:
        """Add an item to the context. Returns False if it won't fit."""
        tokens = self.estimate_tokens(content)

        item = ContextItem(
            id=id,
            content=content,
            tokens=tokens,
            priority=priority,
            kind=kind,
            can_summarize=can_summarize,
            can_drop=can_drop,
        )

        self.items.append(item)
        self._token_count += tokens

        # If over budget, trim
        if self._token_count > self.available_tokens:
            self._trim()

        return True

    def _trim(self) -> None:
        """Trim context to fit within token budget."""
        # Sort by priority (lowest first = droppable)
        droppable = [
            item for item in self.items
            if item.can_drop and item.kind not in ("system",)
        ]
        droppable.sort(key=lambda x: x.priority)

        # Drop lowest priority items first
        for item in droppable:
            if self._token_count <= self.available_tokens:
                break
            self.items.remove(item)
            self._token_count -= item.tokens

        # If still over, summarize old messages
        if self._token_count > self.available_tokens:
            self._summarize_old()

        # If still over, truncate oldest tool results
        if self._token_count > self.available_tokens:
            self._truncate_old()

    def _summarize_old(self) -> None:
        """Summarize old messages to reduce token count."""
        # Find summarizable items (old messages, not system)
        summarizable = [
            item for item in self.items
            if item.can_summarize and item.kind in ("message", "tool_result")
        ]

        # Summarize the oldest items
        for item in summarizable[:3]:
            if self._token_count <= self.available_tokens:
                break
            old_tokens = item.tokens
            # Create a summary (truncated version)
            summary = item.content[:200] + "..." if len(item.content) > 250 else item.content
            new_tokens = self.estimate_tokens(summary)

            if new_tokens < old_tokens:
                item.content = f"[Summarized] {summary}"
                item.tokens = new_tokens
                self._token_count -= (old_tokens - new_tokens)

    def _truncate_old(self) -> None:
        """Truncate old tool results."""
        tool_results = [
            item for item in self.items
            if item.kind == "tool_result" and len(item.content) > 500
        ]

        for item in tool_results:
            if self._token_count <= self.available_tokens:
                break
            old_tokens = item.tokens
            # Keep first and last 200 chars
            truncated = item.content[:200] + f"\n... ({len(item.content)} chars truncated) ...\n" + item.content[-200:]
            new_tokens = self.estimate_tokens(truncated)

            if new_tokens < old_tokens:
                item.content = truncated
                item.tokens = new_tokens
                self._token_count -= (old_tokens - new_tokens)

    def get_messages(self) -> list[dict]:
        """Get the context as a list of messages for the LLM."""
        messages = []
        for item in self.items:
            messages.append({
                "role": "user" if item.kind == "message" else "system",
                "content": item.content,
            })
        return messages

    @property
    def token_count(self) -> int:
        return self._token_count

    @property
    def remaining_tokens(self) -> int:
        return self.available_tokens - self._token_count

    @property
    def utilization(self) -> float:
        return self._token_count / self.available_tokens if self.available_tokens else 0.0

    def stats(self) -> dict:
        return {
            "total_tokens": self._token_count,
            "max_tokens": self.max_tokens,
            "available_tokens": self.available_tokens,
            "remaining_tokens": self.remaining_tokens,
            "utilization": f"{self.utilization:.1%}",
            "items": len(self.items),
        }


class ConversationContext:
    """
    Manages conversation context with intelligent pruning.
    Wraps ContextWindowManager for conversation-specific logic.
    """

    def __init__(self, max_tokens: int = 32000):
        self.manager = ContextWindowManager(max_tokens)
        self._message_count = 0
        self._system_prompt = ""

    def set_system(self, prompt: str) -> None:
        """Set the system prompt (always included)."""
        self._system_prompt = prompt
        self.manager.add(
            id="system",
            content=prompt,
            priority=1.0,
            kind="system",
            can_summarize=False,
            can_drop=False,
        )

    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self._message_count += 1
        self.manager.add(
            id=f"user_{self._message_count}",
            content=content,
            priority=0.8,
            kind="message",
        )

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message."""
        self._message_count += 1
        self.manager.add(
            id=f"assistant_{self._message_count}",
            content=content,
            priority=0.7,
            kind="message",
        )

    def add_tool_result(self, tool_name: str, result: str, priority: float = 0.4) -> None:
        """Add a tool result."""
        self._message_count += 1
        self.manager.add(
            id=f"tool_{self._message_count}",
            content=f"[{tool_name}] {result}",
            priority=priority,
            kind="tool_result",
            can_drop=True,
        )

    def add_file_context(self, filepath: str, content: str) -> None:
        """Add file content as context."""
        self.manager.add(
            id=f"file_{filepath}",
            content=f"--- {filepath} ---\n{content}",
            priority=0.3,
            kind="file",
            can_drop=True,
        )

    def add_code_context(self, description: str, code: str) -> None:
        """Add code snippet as context."""
        self.manager.add(
            id=f"code_{description}",
            content=f"{description}:\n```\n{code}\n```",
            priority=0.5,
            kind="code",
            can_drop=True,
        )

    def to_messages(self) -> list[dict]:
        """Convert to LLM message format."""
        return self.manager.get_messages()

    @property
    def is_near_limit(self) -> bool:
        return self.manager.utilization > 0.85

    @property
    def stats(self) -> dict:
        return self.manager.stats()
