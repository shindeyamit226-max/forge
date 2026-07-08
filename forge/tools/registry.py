"""
Tool registry — discover, register, and execute tools.
Supports decorators, auto-discovery, and parameter validation.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_type_hints

from ..llm.base import ToolDefinition


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None
    artifacts: list[str] = field(default_factory=list)  # Files created/modified

    def to_string(self) -> str:
        if self.success:
            return str(self.output)
        return f"ERROR: {self.error}"


@dataclass
class Tool:
    """A registered tool with metadata and execution logic."""
    name: str
    description: str
    func: Callable
    parameters: dict  # JSON Schema
    dangerous: bool = False
    requires_approval: bool = False
    category: str = "general"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""
        try:
            if asyncio.iscoroutinefunction(self.func):
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)

            if isinstance(result, ToolResult):
                return result
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
            )


def _python_type_to_json_schema(t) -> dict:
    """Convert Python type annotation to JSON Schema."""
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }

    if t in type_map:
        return type_map[t]

    origin = getattr(t, "__origin__", None)
    if origin is list:
        args = getattr(t, "__args__", [])
        item_schema = _python_type_to_json_schema(args[0]) if args else {}
        return {"type": "array", "items": item_schema}
    if origin is dict:
        return {"type": "object"}
    if origin is type(None) or t is type(None):
        return {}

    return {"type": "string"}


def _build_schema_from_func(func: Callable) -> dict:
    """Build JSON Schema from function signature and type hints."""
    sig = inspect.signature(func)
    hints = get_type_hints(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        schema = _python_type_to_json_schema(hints.get(name, str))

        # Check for default value
        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default
        else:
            required.append(name)

        # Check for docstring-based description
        properties[name] = schema

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class ToolRegistry:
    """Global tool registry — discover, register, execute tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, list[str]] = {}

    def register(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict] = None,
        dangerous: bool = False,
        requires_approval: bool = False,
        category: str = "general",
    ) -> Callable:
        """Decorator to register a function as a tool."""
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "").strip().split("\n")[0]
            tool_params = parameters or _build_schema_from_func(func)

            tool = Tool(
                name=tool_name,
                description=tool_desc,
                func=func,
                parameters=tool_params,
                dangerous=dangerous,
                requires_approval=requires_approval,
                category=category,
            )
            self._tools[tool_name] = tool

            if category not in self._categories:
                self._categories[category] = []
            if tool_name not in self._categories[category]:
                self._categories[category].append(tool_name)

            return func
        return decorator

    def add_tool(self, tool: Tool) -> None:
        """Directly register a Tool object."""
        self._tools[tool.name] = tool
        cat = tool.category
        if cat not in self._categories:
            self._categories[cat] = []
        if tool.name not in self._categories[cat]:
            self._categories[cat].append(tool.name)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Unknown tool: {name}. Available: {', '.join(sorted(self._tools.keys()))}",
            )
        return await tool.execute(**arguments)

    @property
    def definitions(self) -> list[ToolDefinition]:
        """Get all tool definitions for the LLM."""
        return [t.definition for t in self._tools.values()]

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def by_category(self, category: str) -> list[Tool]:
        names = self._categories.get(category, [])
        return [self._tools[n] for n in names if n in self._tools]

    @property
    def categories(self) -> list[str]:
        return sorted(self._categories.keys())

    def summary(self) -> str:
        """Human-readable summary of available tools."""
        lines = []
        for cat in sorted(self._categories.keys()):
            tools = self.by_category(cat)
            lines.append(f"\n  [{cat}]")
            for t in tools:
                danger = " ⚠️" if t.dangerous else ""
                lines.append(f"    {t.name}: {t.description}{danger}")
        return "\n".join(lines)


# Global registry instance
registry = ToolRegistry()


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[dict] = None,
    dangerous: bool = False,
    requires_approval: bool = False,
    category: str = "general",
) -> Callable:
    """Convenience decorator using the global registry."""
    return registry.register(
        name=name,
        description=description,
        parameters=parameters,
        dangerous=dangerous,
        requires_approval=requires_approval,
        category=category,
    )
