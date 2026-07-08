"""
Hook System — event-driven plugin architecture.
Plugins can hook into: pre_tool, post_tool, pre_edit, post_edit, on_error, on_save.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Hook:
    """A registered hook."""
    name: str
    event: str
    callback: Callable
    priority: int = 0  # Lower = runs first
    enabled: bool = True


class HookRegistry:
    """Registry for event hooks."""

    EVENTS = [
        "pre_tool",      # Before tool execution
        "post_tool",     # After tool execution
        "pre_edit",      # Before file edit
        "post_edit",     # After file edit
        "pre_commit",    # Before git commit
        "post_commit",   # After git commit
        "on_error",      # On error
        "on_save",       # On file save
        "on_load",       # On file load
        "on_test",       # On test run
        "on_build",      # On build
        "on_deploy",     # On deploy
    ]

    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {event: [] for event in self.EVENTS}

    def register(self, event: str, callback: Callable, name: str = "", priority: int = 0) -> Hook:
        """Register a hook for an event."""
        if event not in self.EVENTS:
            raise ValueError(f"Unknown event: {event}. Available: {', '.join(self.EVENTS)}")

        hook = Hook(
            name=name or callback.__name__,
            event=event,
            callback=callback,
            priority=priority,
        )
        self._hooks[event].append(hook)
        self._hooks[event].sort(key=lambda h: h.priority)
        return hook

    def unregister(self, name: str) -> bool:
        """Unregister a hook by name."""
        for event in self.EVENTS:
            self._hooks[event] = [h for h in self._hooks[event] if h.name != name]
        return True

    async def trigger(self, event: str, context: dict = None) -> dict:
        """Trigger all hooks for an event."""
        if event not in self.EVENTS:
            return context or {}

        ctx = context or {}
        for hook in self._hooks[event]:
            if not hook.enabled:
                continue
            try:
                result = hook.callback(ctx)
                if result is not None:
                    ctx = result
            except Exception as e:
                ctx["error"] = str(e)

        return ctx

    def list_hooks(self, event: Optional[str] = None) -> list[Hook]:
        """List registered hooks."""
        if event:
            return self._hooks.get(event, [])
        return [h for hooks in self._hooks.values() for h in hooks]

    def disable(self, name: str) -> None:
        for hooks in self._hooks.values():
            for hook in hooks:
                if hook.name == name:
                    hook.enabled = False

    def enable(self, name: str) -> None:
        for hooks in self._hooks.values():
            for hook in hooks:
                if hook.name == name:
                    hook.enabled = True
