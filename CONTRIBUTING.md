# Contributing to Forge

Thank you for your interest in contributing to Forge! 🎉

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a virtual environment
4. Install in development mode

```bash
git clone https://github.com/YOUR_USERNAME/forge.git
cd forge
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Development

### Running Tests
```bash
pytest tests/ -v
```

### Code Style
We use `ruff` for linting:
```bash
ruff check .
ruff format .
```

### Adding a New Tool

1. Open `forge/tools/builtin.py`
2. Use the `@registry.register` decorator:

```python
@registry.register(
    name="my_tool",
    description="What this tool does (shown to the LLM)",
    parameters={
        "type": "object",
        "properties": {
            "arg1": {"type": "string", "description": "What this arg does"},
        },
        "required": ["arg1"],
    },
    category="my_category",
    dangerous=False,  # Set True if it needs user approval
)
async def my_tool(arg1: str) -> ToolResult:
    # Your implementation
    return ToolResult(success=True, output="result")
```

### Adding a New LLM Provider

1. Create `forge/llm/providers/my_provider.py`
2. Implement the `LLMProvider` abstract class
3. Register it in `forge/llm/providers/__init__.py`

### Project Structure

```
forge/
├── cli.py              # CLI entry point and interactive mode
├── config.py           # Configuration management
├── session.py          # Session persistence
├── plugins.py          # Plugin loader
├── core/
│   ├── agent.py        # Main agent engine (the brain)
│   ├── context.py      # Project analysis and context
│   └── planner.py      # Task planning and re-planning
├── llm/
│   ├── base.py         # Abstract LLM provider interface
│   └── providers/      # Provider implementations
├── tools/
│   ├── registry.py     # Tool registration system
│   └── builtin.py      # Built-in tools
└── tui/
    └── display.py      # Terminal UI
```

## Pull Request Process

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation if needed
6. Submit a PR with a clear description

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to build great tools.

## Questions?

Open an issue or start a discussion. We're happy to help!
