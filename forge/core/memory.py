"""
Session Memory — learn from past interactions, user preferences, patterns.
Forge remembers what worked and adapts over time.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    content: str
    kind: str  # preference, pattern, solution, fact
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = 0.0
    relevance: float = 1.0  # Decays over time
    tags: list[str] = field(default_factory=list)

    def access(self) -> None:
        self.access_count += 1
        self.last_accessed = time.time()


class SessionMemory:
    """
    Persistent memory across sessions.
    Learns user preferences, coding patterns, and solutions.
    """

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memories: dict[str, MemoryEntry] = {}
        self._load()

    def _memory_path(self) -> Path:
        return self.memory_dir / "memory.json"

    def _load(self) -> None:
        """Load memories from disk."""
        path = self._memory_path()
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            for key, entry_data in data.items():
                self.memories[key] = MemoryEntry(
                    key=key,
                    content=entry_data["content"],
                    kind=entry_data.get("kind", "fact"),
                    timestamp=entry_data.get("timestamp", 0),
                    access_count=entry_data.get("access_count", 0),
                    last_accessed=entry_data.get("last_accessed", 0),
                    relevance=entry_data.get("relevance", 1.0),
                    tags=entry_data.get("tags", []),
                )
        except Exception:
            pass

    def _save(self) -> None:
        """Save memories to disk."""
        data = {}
        for key, entry in self.memories.items():
            data[key] = {
                "content": entry.content,
                "kind": entry.kind,
                "timestamp": entry.timestamp,
                "access_count": entry.access_count,
                "last_accessed": entry.last_accessed,
                "relevance": entry.relevance,
                "tags": entry.tags,
            }

        self._memory_path().write_text(json.dumps(data, indent=2))

    def remember(self, key: str, content: str, kind: str = "fact", tags: list[str] = None) -> None:
        """Store a memory."""
        self.memories[key] = MemoryEntry(
            key=key,
            content=content,
            kind=kind,
            tags=tags or [],
        )
        self._save()

    def recall(self, key: str) -> Optional[str]:
        """Recall a specific memory."""
        entry = self.memories.get(key)
        if entry:
            entry.access()
            self._save()
            return entry.content
        return None

    def search(self, query: str, kind: Optional[str] = None, limit: int = 5) -> list[MemoryEntry]:
        """Search memories by relevance."""
        query_lower = query.lower()
        results = []

        for entry in self.memories.values():
            if kind and entry.kind != kind:
                continue

            # Score based on content match
            score = 0.0
            content_lower = entry.content.lower()

            # Exact match
            if query_lower in content_lower:
                score += 5.0

            # Word overlap
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            overlap = query_words & content_words
            if overlap:
                score += len(overlap) * 2.0

            # Tag match
            for tag in entry.tags:
                if tag.lower() in query_lower:
                    score += 3.0

            # Recency boost
            age_hours = (time.time() - entry.timestamp) / 3600
            if age_hours < 24:
                score *= 1.5
            elif age_hours < 168:  # 1 week
                score *= 1.2

            # Access frequency boost
            if entry.access_count > 0:
                score *= (1 + min(entry.access_count * 0.1, 0.5))

            if score > 0:
                results.append((score, entry))

        results.sort(reverse=True, key=lambda x: x[0])
        return [entry for _, entry in results[:limit]]

    def learn_preference(self, key: str, value: str) -> None:
        """Learn a user preference."""
        self.remember(f"pref:{key}", value, kind="preference", tags=["preference"])

    def learn_pattern(self, pattern: str, description: str) -> None:
        """Learn a coding pattern."""
        self.remember(f"pattern:{pattern}", description, kind="pattern", tags=["pattern"])

    def learn_solution(self, problem: str, solution: str) -> None:
        """Learn a solution to a problem."""
        self.remember(f"solution:{problem}", solution, kind="solution", tags=["solution"])

    def get_preferences(self) -> dict[str, str]:
        """Get all user preferences."""
        return {
            k.replace("pref:", ""): v.content
            for k, v in self.memories.items()
            if v.kind == "preference"
        }

    def get_context_summary(self, query: str = "") -> str:
        """Get a summary of relevant memories for context."""
        if query:
            memories = self.search(query, limit=5)
        else:
            # Get most recent/accessed memories
            memories = sorted(
                self.memories.values(),
                key=lambda m: (m.access_count, m.timestamp),
                reverse=True,
            )[:10]

        if not memories:
            return ""

        parts = ["Relevant context from memory:"]
        for m in memories:
            parts.append(f"  [{m.kind}] {m.key}: {m.content[:200]}")

        return "\n".join(parts)

    def forget(self, key: str) -> bool:
        """Remove a memory."""
        if key in self.memories:
            del self.memories[key]
            self._save()
            return True
        return False

    def clear(self) -> None:
        """Clear all memories."""
        self.memories.clear()
        self._save()

    @property
    def count(self) -> int:
        return len(self.memories)

    def stats(self) -> dict:
        kinds = {}
        for m in self.memories.values():
            kinds[m.kind] = kinds.get(m.kind, 0) + 1
        return {
            "total": self.count,
            "by_kind": kinds,
        }
