"""Basic tests for Forge core functionality."""

import pytest
import asyncio
from pathlib import Path

from forge.config import Config
from forge.tools.registry import ToolRegistry, Tool, ToolResult, tool
from forge.core.context import ProjectContext


class TestConfig:
    def test_defaults(self):
        config = Config()
        assert config.provider == "ollama"
        assert config.model == "codellama:13b"
        assert config.temperature == 0.1
        assert config.max_iterations == 30

    def test_override(self):
        config = Config()
        config.override("model", "llama3")
        assert config.get("model") == "llama3"


class TestToolRegistry:
    def test_register_decorator(self):
        registry = ToolRegistry()

        @registry.register(name="test_tool", description="A test tool", category="test")
        def my_tool(x: str) -> str:
            return f"result: {x}"

        assert "test_tool" in registry.tool_names
        tool_obj = registry.get("test_tool")
        assert tool_obj is not None
        assert tool_obj.description == "A test tool"
        assert tool_obj.category == "test"

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        registry = ToolRegistry()

        @registry.register(name="add", description="Add two numbers")
        def add(a: int, b: int) -> int:
            return a + b

        result = await registry.execute("add", {"a": 2, "b": 3})
        assert result.success is True
        assert result.output == 5

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        registry = ToolRegistry()

        @registry.register(name="fail", description="Always fails")
        def fail():
            raise ValueError("test error")

        result = await registry.execute("fail", {})
        assert result.success is False
        assert "test error" in result.error

    def test_definitions(self):
        registry = ToolRegistry()

        @registry.register(name="echo", description="Echo input")
        def echo(text: str) -> str:
            return text

        defs = registry.definitions
        assert len(defs) == 1
        assert defs[0].name == "echo"

    def test_categories(self):
        registry = ToolRegistry()

        @registry.register(name="a", description="A", category="cat1")
        def a():
            pass

        @registry.register(name="b", description="B", category="cat2")
        def b():
            pass

        @registry.register(name="c", description="C", category="cat1")
        def c():
            pass

        assert "cat1" in registry.categories
        assert "cat2" in registry.categories
        assert len(registry.by_category("cat1")) == 2


class TestProjectContext:
    def test_detect_language(self):
        assert ProjectContext._detect_language(".py") == "python"
        assert ProjectContext._detect_language(".js") == "javascript"
        assert ProjectContext._detect_language(".rs") == "rust"
        assert ProjectContext._detect_language(".xyz") is None

    def test_scan_current_dir(self):
        ctx = ProjectContext()
        ctx.scan(Path(__file__).parent.parent)
        # Should find at least the Python files in the project
        assert len(ctx.files) > 0
        assert "python" in ctx.languages


class TestToolResult:
    def test_success(self):
        result = ToolResult(success=True, output="hello")
        assert result.to_string() == "hello"

    def test_failure(self):
        result = ToolResult(success=False, output=None, error="bad")
        assert "ERROR" in result.to_string()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
