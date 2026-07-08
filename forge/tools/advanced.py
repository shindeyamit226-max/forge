"""
Advanced tools — AST search, semantic search, error analysis, git workflow, memory.
These are the tools that make Forge genuinely superior.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from .registry import ToolResult, registry


# ============================================================
# AST-AWARE CODE TOOLS
# ============================================================

@registry.register(
    name="find_symbol",
    description="Find a function, class, or method by name across the codebase. Uses AST parsing for precise results. Returns the symbol's location, signature, and surrounding code.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Symbol name to find (e.g. 'UserService', 'handle_login', 'processPayment')"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
        },
        "required": ["name"],
    },
    category="code",
)
async def find_symbol(name: str, path: str = ".") -> ToolResult:
    """Find a symbol by name using AST parsing."""
    from ..core.ast_editor import find_symbol_in_project, parse_file

    results = find_symbol_in_project(path, name)
    if not results:
        return ToolResult(success=True, output=f"No symbol '{name}' found in {path}")

    lines = [f"Found {len(results)} match(es) for '{name}':\n"]
    for sym in results[:10]:
        kind_icon = {"function": "⚡", "class": "🏗️", "method": "🔧", "variable": "📦"}.get(sym.kind, "📍")
        parent = f" (in {sym.parent})" if sym.parent else ""
        params = f"({', '.join(sym.params)})" if sym.params else ""
        ret = f" -> {sym.return_type}" if sym.return_type else ""

        lines.append(f"  {kind_icon} {sym.kind} {sym.name}{parent}")
        lines.append(f"    File: {sym.file}:{sym.line}")
        if params:
            lines.append(f"    Signature: {sym.name}{params}{ret}")
        if sym.decorators:
            lines.append(f"    Decorators: {', '.join(sym.decorators)}")
        if sym.docstring:
            lines.append(f"    Doc: {sym.docstring[:200]}")
        lines.append("")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="get_function",
    description="Extract the source code of a specific function or method. Use this to read a function's implementation without reading the entire file.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Function/method name"},
            "file": {"type": "string", "description": "File path (optional, searches project if omitted)", "default": ""},
        },
        "required": ["name"],
    },
    category="code",
)
async def get_function(name: str, file: str = "") -> ToolResult:
    """Extract a function's source code."""
    from ..core.ast_editor import parse_file, PythonASTParser

    if file:
        # Look in specific file
        parser = PythonASTParser()
        source = Path(file).read_text(errors="replace")
        body = parser.get_function_body(source, name)
        if body:
            return ToolResult(success=True, output=f"--- {name} in {file} ---\n{body}")
        return ToolResult(success=False, output=None, error=f"Function '{name}' not found in {file}")

    # Search project
    from ..core.ast_editor import find_symbol_in_project
    results = find_symbol_in_project(".", name)
    if not results:
        return ToolResult(success=False, output=None, error=f"Function '{name}' not found")

    sym = results[0]
    parser = PythonASTParser()
    source = Path(sym.file).read_text(errors="replace")
    body = parser.get_function_body(source, name)
    if body:
        return ToolResult(success=True, output=f"--- {name} in {sym.file} ---\n{body}")

    return ToolResult(success=False, output=None, error=f"Could not extract function body")


@registry.register(
    name="semantic_search",
    description="Search the codebase by meaning, not just keywords. Finds relevant code even when exact words don't match. Uses TF-IDF + BM25 ranking for fast, accurate results.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language query (e.g. 'how does authentication work', 'database connection setup')"},
            "top_k": {"type": "integer", "description": "Number of results", "default": 5},
            "language": {"type": "string", "description": "Filter by language (python, javascript, etc.)", "default": ""},
        },
        "required": ["query"],
    },
    category="search",
)
async def semantic_search(query: str, top_k: int = 5, language: str = "") -> ToolResult:
    """Semantic code search using BM25."""
    from ..core.indexer import CodeIndexer

    indexer = CodeIndexer()

    # Index the current directory
    import time
    start = time.monotonic()
    files_indexed = indexer.index_directory(".")
    index_time = time.monotonic() - start

    # Search
    results = indexer.search(
        query,
        top_k=top_k,
        language=language if language else None,
    )

    if not results:
        return ToolResult(success=True, output=f"No results for: {query}")

    lines = [f"Found {len(results)} results (indexed {files_indexed} files in {index_time:.1f}s):\n"]
    for i, result in enumerate(results, 1):
        chunk = result.chunk
        symbols = f" [{', '.join(chunk.symbols)}]" if chunk.symbols else ""
        lines.append(f"  {i}. {chunk.file}:{chunk.start_line}-{chunk.end_line}{symbols}")
        lines.append(f"     Score: {result.score:.2f} | Type: {chunk.chunk_type} | Lang: {chunk.language}")
        # Show first few lines of content
        preview = chunk.content[:300].replace("\n", "\n     ")
        lines.append(f"     {preview}")
        lines.append("")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="analyze_errors",
    description="Parse and analyze error output from compilers, test runners, or linters. Understands Python, JavaScript, TypeScript, Go, Rust. Returns structured error analysis with root cause and fix strategy.",
    parameters={
        "type": "object",
        "properties": {
            "output": {"type": "string", "description": "Error output to analyze (from compiler, test runner, linter, etc.)"},
            "language": {"type": "string", "description": "Language hint (python, javascript, go, rust, auto)", "default": "auto"},
        },
        "required": ["output"],
    },
    category="analysis",
)
async def analyze_errors(output: str, language: str = "auto") -> ToolResult:
    """Parse and analyze error output."""
    from ..core.error_recovery import ErrorRecoveryEngine

    engine = ErrorRecoveryEngine()
    analysis = engine.analyze(output, language)

    if not analysis.errors:
        return ToolResult(success=True, output="No errors found in the output.")

    return ToolResult(success=True, output=analysis.summary())


@registry.register(
    name="git_workflow",
    description="Execute intelligent git operations. Supports: status, diff, log, commit, branch, stash, blame. Provides richer output than raw git commands.",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Git action to perform",
                "enum": ["status", "diff", "log", "commit", "branch", "stash", "stash_pop", "blame", "recent_changes"],
            },
            "args": {"type": "string", "description": "Additional arguments", "default": ""},
            "message": {"type": "string", "description": "Commit message (for commit action)", "default": ""},
            "file": {"type": "string", "description": "File path (for diff/blame/log)", "default": ""},
        },
        "required": ["action"],
    },
    category="git",
)
async def git_workflow(action: str, args: str = "", message: str = "", file: str = "") -> ToolResult:
    """Intelligent git operations."""
    from ..core.git_workflow import GitWorkflow

    gw = GitWorkflow()

    if not await gw.is_git_repo():
        return ToolResult(success=False, output=None, error="Not a git repository")

    try:
        if action == "status":
            status = await gw.status()
            return ToolResult(success=True, output=status.summary())

        elif action == "diff":
            diff = await gw.diff(staged="staged" in args, file=file or None)
            if not diff:
                return ToolResult(success=True, output="No changes")
            return ToolResult(success=True, output=diff[:10000])

        elif action == "log":
            count = 10
            if args and args.isdigit():
                count = int(args)
            commits = await gw.log(count, file=file or None)
            lines = []
            for c in commits:
                files_str = f" ({len(c.files)} files)" if c.files else ""
                lines.append(f"  {c.hash} {c.date[:10]} {c.author}: {c.message}{files_str}")
            return ToolResult(success=True, output="\n".join(lines) or "No commits found")

        elif action == "commit":
            if not message:
                return ToolResult(success=False, output=None, error="Commit message required")
            success, output = await gw.auto_commit(message)
            return ToolResult(success=success, output=output)

        elif action == "branch":
            if args:
                success = await gw.create_branch(args)
                return ToolResult(success=success, output=f"Created branch: {args}" if success else "Failed to create branch")
            else:
                out, _, _ = await gw._run("branch", "-a")
                return ToolResult(success=True, output=out or "No branches")

        elif action == "stash":
            success = await gw.stash(message)
            return ToolResult(success=success, output="Changes stashed" if success else "Nothing to stash")

        elif action == "stash_pop":
            success = await gw.stash_pop()
            return ToolResult(success=success, output="Stash popped" if success else "No stash to pop")

        elif action == "blame":
            if not file:
                return ToolResult(success=False, output=None, error="File path required for blame")
            blames = await gw.blame(file)
            lines = [f"Blame for {file}:"]
            for b in blames[:50]:
                lines.append(f"  {b.hash} {b.author:20s} {b.content}")
            return ToolResult(success=True, output="\n".join(lines))

        elif action == "recent_changes":
            summary = await gw.get_recent_changes_summary()
            return ToolResult(success=True, output=summary)

        else:
            return ToolResult(success=False, output=None, error=f"Unknown action: {action}")

    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="remember",
    description="Store information in Forge's persistent memory. Use this to remember user preferences, coding patterns, solutions, or facts about the project.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Memory key (e.g. 'user_prefers_tabs', 'auth_pattern', 'db_connection')"},
            "content": {"type": "string", "description": "Content to remember"},
            "kind": {"type": "string", "description": "Type of memory", "enum": ["preference", "pattern", "solution", "fact"], "default": "fact"},
        },
        "required": ["key", "content"],
    },
    category="memory",
)
async def remember(key: str, content: str, kind: str = "fact") -> ToolResult:
    """Store a memory."""
    from ..core.memory import SessionMemory
    from ..config import FORGE_HOME

    memory = SessionMemory(FORGE_HOME / "memory")
    memory.remember(key, content, kind)
    return ToolResult(success=True, output=f"Remembered: {key}")


@registry.register(
    name="recall",
    description="Search Forge's memory for relevant information. Use this to recall user preferences, past solutions, or project facts.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for in memory"},
        },
        "required": ["query"],
    },
    category="memory",
)
async def recall(query: str) -> ToolResult:
    """Search memories."""
    from ..core.memory import SessionMemory
    from ..config import FORGE_HOME

    memory = SessionMemory(FORGE_HOME / "memory")
    results = memory.search(query)

    if not results:
        return ToolResult(success=True, output=f"No memories found for: {query}")

    lines = [f"Found {len(results)} relevant memories:\n"]
    for m in results:
        lines.append(f"  [{m.kind}] {m.key}: {m.content[:200]}")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="explain_code",
    description="Explain a piece of code, function, or concept in plain English. Use this when you need to understand what code does before modifying it.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code to explain (or file path)"},
            "question": {"type": "string", "description": "Specific question about the code", "default": ""},
        },
        "required": ["code"],
    },
    category="reasoning",
)
async def explain_code(code: str, question: str = "") -> ToolResult:
    """Explain code — this is a pass-through for the LLM to reason about."""
    # This tool's real value is in the prompt — the LLM will explain
    prompt = f"Explain this code:\n```\n{code}\n```"
    if question:
        prompt += f"\n\nSpecifically: {question}"
    return ToolResult(success=True, output=prompt)
