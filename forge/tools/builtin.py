"""
Built-in tools — file ops, shell, search, git, analysis.
These are the tools Forge uses to interact with your codebase.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from .registry import ToolResult, registry


# ============================================================
# FILE OPERATIONS
# ============================================================

@registry.register(
    name="read",
    description="Read the contents of a file. Returns the file content with line numbers. Use offset and limit for large files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
            "offset": {"type": "integer", "description": "Line number to start from (1-indexed)", "default": 1},
            "limit": {"type": "integer", "description": "Maximum number of lines to read", "default": 500},
        },
        "required": ["path"],
    },
    category="file",
)
async def read_file(path: str, offset: int = 1, limit: int = 500) -> ToolResult:
    """Read file contents with line numbers."""
    p = Path(path).expanduser()
    if not p.exists():
        return ToolResult(success=False, output=None, error=f"File not found: {path}")
    if not p.is_file():
        return ToolResult(success=False, output=None, error=f"Not a file: {path}")

    try:
        content = p.read_text(errors="replace")
        lines = content.splitlines()

        # Apply offset and limit
        start = max(0, offset - 1)
        end = min(len(lines), start + limit)
        selected = lines[start:end]

        # Add line numbers
        numbered = []
        for i, line in enumerate(selected, start=start + 1):
            numbered.append(f"{i:4d} | {line}")

        result = "\n".join(numbered)

        # Add metadata
        total = len(lines)
        if end < total:
            result += f"\n... ({total - end} more lines, {total} total)"

        return ToolResult(success=True, output=result)
    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="write",
    description="Write content to a file. Creates the file and any parent directories if they don't exist. Overwrites existing files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["path", "content"],
    },
    category="file",
)
async def write_file(path: str, content: str) -> ToolResult:
    """Write content to a file."""
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        lines = content.count("\n") + 1
        return ToolResult(
            success=True,
            output=f"Wrote {len(content)} bytes ({lines} lines) to {path}",
            artifacts=[str(p)],
        )
    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="edit",
    description="Edit a file by replacing exact text. The old_text must match exactly (including whitespace). Use this for surgical edits to existing files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_text": {"type": "string", "description": "Exact text to find and replace (must match exactly)"},
            "new_text": {"type": "string", "description": "Replacement text"},
        },
        "required": ["path", "old_text", "new_text"],
    },
    category="file",
)
async def edit_file(path: str, old_text: str, new_text: str) -> ToolResult:
    """Replace exact text in a file."""
    p = Path(path).expanduser()
    if not p.exists():
        return ToolResult(success=False, output=None, error=f"File not found: {path}")

    try:
        content = p.read_text(errors="replace")

        count = content.count(old_text)
        if count == 0:
            # Try to help with common issues
            suggestions = []
            stripped = old_text.strip()
            if stripped in content:
                suggestions.append("Text exists but with different leading/trailing whitespace")
            elif old_text.replace("\r\n", "\n") in content:
                suggestions.append("Text exists but with different line endings (CRLF vs LF)")

            msg = f"Text not found in {path}"
            if suggestions:
                msg += f". Hint: {suggestions[0]}"
            return ToolResult(success=False, output=None, error=msg)

        if count > 1:
            new_content = content.replace(old_text, new_text, 1)
            msg = f"Replaced first of {count} occurrences"
        else:
            new_content = content.replace(old_text, new_text)
            msg = "Replaced 1 occurrence"

        p.write_text(new_content)
        return ToolResult(
            success=True,
            output=msg,
            artifacts=[str(p)],
        )
    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="multi_edit",
    description="Apply multiple edits to a file in sequence. More efficient than multiple edit calls.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    "required": ["old_text", "new_text"],
                },
                "description": "List of edits to apply in order",
            },
        },
        "required": ["path", "edits"],
    },
    category="file",
)
async def multi_edit_file(path: str, edits: list[dict]) -> ToolResult:
    """Apply multiple edits to a file in sequence."""
    p = Path(path).expanduser()
    if not p.exists():
        return ToolResult(success=False, output=None, error=f"File not found: {path}")

    try:
        content = p.read_text(errors="replace")
        applied = 0
        errors = []

        for i, edit in enumerate(edits):
            old = edit["old_text"]
            new = edit["new_text"]
            if old in content:
                content = content.replace(old, new, 1)
                applied += 1
            else:
                errors.append(f"Edit {i+1}: text not found")

        p.write_text(content)

        if errors:
            return ToolResult(
                success=True,
                output=f"Applied {applied}/{len(edits)} edits. Errors: {'; '.join(errors)}",
                artifacts=[str(p)],
            )
        return ToolResult(
            success=True,
            output=f"Applied all {applied} edits successfully",
            artifacts=[str(p)],
        )
    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="create",
    description="Create a new file with content. Fails if the file already exists (use write to overwrite).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path for the new file"},
            "content": {"type": "string", "description": "File content", "default": ""},
        },
        "required": ["path"],
    },
    category="file",
)
async def create_file(path: str, content: str = "") -> ToolResult:
    """Create a new file."""
    p = Path(path).expanduser()
    if p.exists():
        return ToolResult(success=False, output=None, error=f"File already exists: {path}. Use 'write' to overwrite.")

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        lines = content.count("\n") + 1 if content else 0
        return ToolResult(
            success=True,
            output=f"Created {path} ({lines} lines)",
            artifacts=[str(p)],
        )
    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="list_dir",
    description="List files and directories in a path. Shows file sizes and types.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list", "default": "."},
            "show_hidden": {"type": "boolean", "description": "Include hidden files", "default": False},
            "max_items": {"type": "integer", "description": "Max items to show", "default": 100},
        },
    },
    category="file",
)
async def list_directory(path: str = ".", show_hidden: bool = False, max_items: int = 100) -> ToolResult:
    """List directory contents."""
    p = Path(path).expanduser()
    if not p.exists():
        return ToolResult(success=False, output=None, error=f"Path not found: {path}")
    if not p.is_dir():
        return ToolResult(success=False, output=None, error=f"Not a directory: {path}")

    try:
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))

        if not show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]

        lines = []
        for entry in entries[:max_items]:
            if entry.is_dir():
                try:
                    child_count = sum(1 for _ in entry.iterdir())
                    lines.append(f"📁 {entry.name}/ ({child_count} items)")
                except PermissionError:
                    lines.append(f"📁 {entry.name}/ (permission denied)")
            else:
                size = entry.stat().st_size
                if size > 1024 * 1024:
                    size_str = f"{size // (1024*1024)}MB"
                elif size > 1024:
                    size_str = f"{size // 1024}KB"
                else:
                    size_str = f"{size}B"
                lines.append(f"📄 {entry.name} ({size_str})")

        if len(entries) > max_items:
            lines.append(f"\n... and {len(entries) - max_items} more items")

        return ToolResult(success=True, output="\n".join(lines))
    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


# ============================================================
# SHELL EXECUTION
# ============================================================

DANGEROUS_COMMANDS = {
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){:", "chmod -R 777 /",
    "shutdown", "reboot", "init 0", "init 6", "killall", "pkill -9",
}


@registry.register(
    name="shell",
    description="Execute a shell command. Returns stdout, stderr, and exit code. Use for running tests, builds, git commands, package management, etc.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory", "default": "."},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
        },
        "required": ["command"],
    },
    dangerous=True,
    category="system",
)
async def shell_exec(command: str, cwd: str = ".", timeout: int = 60) -> ToolResult:
    """Execute a shell command."""
    # Safety check
    cmd_lower = command.lower().strip()
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous in cmd_lower:
            return ToolResult(
                success=False,
                output=None,
                error=f"Blocked dangerous command: {command}",
            )

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd if cwd != "." else None,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(
                success=False,
                output=None,
                error=f"Command timed out after {timeout}s: {command}",
            )

        stdout_str = stdout.decode(errors="replace").strip()
        stderr_str = stderr.decode(errors="replace").strip()

        output_parts = []
        if stdout_str:
            # Truncate very long output
            if len(stdout_str) > 10000:
                stdout_str = stdout_str[:5000] + f"\n\n... ({len(stdout_str) - 10000} chars truncated) ...\n\n" + stdout_str[-5000:]
            output_parts.append(f"STDOUT:\n{stdout_str}")
        if stderr_str:
            if len(stderr_str) > 5000:
                stderr_str = stderr_str[:2500] + f"\n\n... truncated ...\n\n" + stderr_str[-2500:]
            output_parts.append(f"STDERR:\n{stderr_str}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                output=output,
                error=f"Exit code: {proc.returncode}",
            )

        return ToolResult(success=True, output=output)

    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


# ============================================================
# SEARCH
# ============================================================

@registry.register(
    name="search",
    description="Search for text patterns across the codebase. Uses ripgrep if available, falls back to grep. Returns matching lines with file paths and line numbers.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
            "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
            "file_pattern": {"type": "string", "description": "File glob pattern (e.g. '*.py')", "default": ""},
            "max_results": {"type": "integer", "description": "Maximum results to return", "default": 50},
        },
        "required": ["pattern"],
    },
    category="search",
)
async def search_code(pattern: str, path: str = ".", file_pattern: str = "", max_results: int = 50) -> ToolResult:
    """Search for patterns in the codebase."""
    # Try ripgrep first, fall back to grep
    try:
        cmd_parts = ["rg", "--no-heading", "--line-number", "--color=never"]
        if file_pattern:
            cmd_parts.extend(["--glob", file_pattern])
        cmd_parts.extend(["-m", str(max_results)])
        cmd_parts.append(pattern)
        if path != ".":
            cmd_parts.append(path)

        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode(errors="replace").strip()

        if not output:
            return ToolResult(success=True, output=f"No matches found for: {pattern}")

        lines = output.splitlines()
        if len(lines) > max_results:
            output = "\n".join(lines[:max_results]) + f"\n\n... ({len(lines) - max_results} more matches)"

        return ToolResult(success=True, output=output)

    except FileNotFoundError:
        # Fall back to grep
        cmd = ["grep", "-rn", "--include", file_pattern or "*", pattern, path]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode(errors="replace").strip()

            if not output:
                return ToolResult(success=True, output=f"No matches found for: {pattern}")

            return ToolResult(success=True, output=output[:10000])
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))

    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


@registry.register(
    name="find_files",
    description="Find files by name pattern. Useful for locating specific files in the project.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Filename pattern (glob or substring)"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "type_filter": {"type": "string", "description": "Filter by type: 'file' or 'dir'", "default": ""},
        },
        "required": ["pattern"],
    },
    category="search",
)
async def find_files(pattern: str, path: str = ".", type_filter: str = "") -> ToolResult:
    """Find files by name pattern."""
    try:
        cmd = ["find", path, "-name", f"*{pattern}*"]
        if type_filter:
            cmd.extend(["-type", type_filter[0]])  # 'f' for file, 'd' for dir

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        output = stdout.decode(errors="replace").strip()

        if not output:
            return ToolResult(success=True, output=f"No files found matching: {pattern}")

        files = output.splitlines()[:100]
        return ToolResult(success=True, output="\n".join(files))

    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


# ============================================================
# GIT OPERATIONS
# ============================================================

@registry.register(
    name="git",
    description="Execute git commands. Supports: status, diff, log, add, commit, branch, checkout, stash, and more.",
    parameters={
        "type": "object",
        "properties": {
            "subcommand": {
                "type": "string",
                "description": "Git subcommand (status, diff, log, add, commit, branch, checkout, stash, etc.)",
            },
            "args": {
                "type": "string",
                "description": "Additional arguments for the git command",
                "default": "",
            },
        },
        "required": ["subcommand"],
    },
    category="git",
)
async def git_command(subcommand: str, args: str = "") -> ToolResult:
    """Execute a git command."""
    dangerous_git = {"push --force", "reset --hard", "clean -fd", "branch -D"}
    full_cmd = f"git {subcommand} {args}".strip()

    for dg in dangerous_git:
        if dg in full_cmd:
            return ToolResult(
                success=False,
                output=None,
                error=f"Blocked dangerous git command: {full_cmd}",
            )

    try:
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        output = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()

        if proc.returncode != 0:
            return ToolResult(success=False, output=output, error=err or f"Exit code: {proc.returncode}")

        result = output or "(no output)"
        return ToolResult(success=True, output=result)

    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))


# ============================================================
# PROJECT ANALYSIS
# ============================================================

@registry.register(
    name="analyze",
    description="Analyze the project structure. Returns a summary of languages, frameworks, dependencies, entry points, and file tree.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project root path", "default": "."},
            "depth": {"type": "integer", "description": "File tree depth", "default": 4},
        },
    },
    category="analysis",
)
async def analyze_project(path: str = ".", depth: int = 4) -> ToolResult:
    """Analyze the project structure."""
    from ..core.context import ProjectContext

    ctx = ProjectContext()
    ctx.scan(Path(path))

    summary = ctx.summary()
    tree = ctx.file_tree(max_depth=depth)

    output = f"{summary}\n\n📁 File Tree:\n{tree}"
    return ToolResult(success=True, output=output)


@registry.register(
    name="count_lines",
    description="Count lines of code by language. Useful for understanding project size.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to analyze", "default": "."},
        },
    },
    category="analysis",
)
async def count_lines(path: str = ".") -> ToolResult:
    """Count lines of code by language."""
    ext_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".jsx": "React JSX", ".tsx": "React TSX", ".rs": "Rust",
        ".go": "Go", ".java": "Java", ".c": "C", ".cpp": "C++",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".kt": "Kotlin", ".scala": "Scala", ".ex": "Elixir",
        ".sh": "Shell", ".sql": "SQL", ".html": "HTML", ".css": "CSS",
        ".md": "Markdown", ".json": "JSON", ".yaml": "YAML",
    }

    stats: dict[str, dict] = {}
    total_files = 0
    total_lines = 0

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ext_map:
                continue

            fpath = os.path.join(root, fname)
            try:
                with open(fpath, errors="replace") as f:
                    lines = sum(1 for _ in f)
            except Exception:
                continue

            lang = ext_map[ext]
            if lang not in stats:
                stats[lang] = {"files": 0, "lines": 0}
            stats[lang]["files"] += 1
            stats[lang]["lines"] += lines
            total_files += 1
            total_lines += lines

    # Format output
    sorted_langs = sorted(stats.items(), key=lambda x: -x[1]["lines"])
    lines_out = [f"{'Language':<15} {'Files':>8} {'Lines':>10}"]
    lines_out.append("-" * 35)
    for lang, s in sorted_langs:
        lines_out.append(f"{lang:<15} {s['files']:>8} {s['lines']:>10}")
    lines_out.append("-" * 35)
    lines_out.append(f"{'TOTAL':<15} {total_files:>8} {total_lines:>10}")

    return ToolResult(success=True, output="\n".join(lines_out))


# ============================================================
# TEST RUNNER
# ============================================================

@registry.register(
    name="test",
    description="Run project tests. Auto-detects the test framework (pytest, jest, cargo test, go test, etc.) and runs appropriate tests.",
    parameters={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Specific test file or pattern to run", "default": ""},
            "verbose": {"type": "boolean", "description": "Run with verbose output", "default": True},
        },
    },
    category="testing",
)
async def run_tests(target: str = "", verbose: bool = True) -> ToolResult:
    """Run project tests."""
    cwd = Path.cwd()

    # Detect test command
    test_commands = []

    if (cwd / "pytest.ini").exists() or (cwd / "conftest.py").exists() or (cwd / "pyproject.toml").exists():
        cmd = ["python", "-m", "pytest"]
        if verbose:
            cmd.append("-v")
        if target:
            cmd.append(target)
        test_commands.append(cmd)

    if (cwd / "package.json").exists():
        try:
            pkg = json.loads((cwd / "package.json").read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                test_commands.append(["npm", "test"])
        except Exception:
            pass

    if (cwd / "Cargo.toml").exists():
        cmd = ["cargo", "test"]
        if verbose:
            cmd.append("--")
            cmd.append("--nocapture")
        test_commands.append(cmd)

    if (cwd / "go.mod").exists():
        cmd = ["go", "test"]
        if verbose:
            cmd.append("-v")
        cmd.append("./...")
        test_commands.append(cmd)

    if not test_commands:
        # Try pytest anyway
        test_commands.append(["python", "-m", "pytest", "-v"] if verbose else ["python", "-m", "pytest"])

    # Run the first available test command
    for cmd in test_commands:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            output = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()

            result_text = output
            if err:
                result_text += f"\n\nSTDERR:\n{err}"

            if proc.returncode == 0:
                return ToolResult(success=True, output=f"✅ Tests passed!\n\n{result_text}")
            else:
                return ToolResult(
                    success=False,
                    output=result_text,
                    error=f"Tests failed with exit code {proc.returncode}",
                )

        except FileNotFoundError:
            continue
        except asyncio.TimeoutError:
            return ToolResult(success=False, output=None, error="Tests timed out after 120s")

    return ToolResult(success=False, output=None, error="No test framework detected")


# ============================================================
# THINKING / REASONING
# ============================================================

@registry.register(
    name="think",
    description="Use this tool to reason through complex problems, analyze code, plan approaches, or explain concepts. The thinking is recorded but takes no physical action.",
    parameters={
        "type": "object",
        "properties": {
            "thought": {"type": "string", "description": "Your reasoning, analysis, or explanation"},
        },
        "required": ["thought"],
    },
    category="reasoning",
)
async def think(thought: str) -> ToolResult:
    """Record a reasoning step."""
    return ToolResult(success=True, output=f"💭 {thought}")


# ============================================================
# HTTP REQUESTS
# ============================================================

@registry.register(
    name="http",
    description="Make HTTP requests. Useful for testing APIs, fetching data, or interacting with web services.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to request"},
            "method": {"type": "string", "description": "HTTP method", "default": "GET", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]},
            "headers": {"type": "object", "description": "Request headers", "default": {}},
            "body": {"type": "string", "description": "Request body (for POST/PUT/PATCH)", "default": ""},
        },
        "required": ["url"],
    },
    category="network",
)
async def http_request(
    url: str, method: str = "GET", headers: dict = None, body: str = ""
) -> ToolResult:
    """Make an HTTP request."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers=headers or {},
                content=body if body else None,
            )

            output_parts = [
                f"HTTP/{resp.http_version} {resp.status_code} {resp.reason_phrase}",
                f"URL: {resp.url}",
            ]

            # Response headers
            for key, val in resp.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    output_parts.append(f"{key}: {val}")

            # Response body
            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    body_json = resp.json()
                    output_parts.append(f"\n{json.dumps(body_json, indent=2)[:5000]}")
                except Exception:
                    output_parts.append(f"\n{resp.text[:5000]}")
            else:
                output_parts.append(f"\n{resp.text[:5000]}")

            success = 200 <= resp.status_code < 400
            return ToolResult(
                success=success,
                output="\n".join(output_parts),
                error=None if success else f"HTTP {resp.status_code}",
            )

    except Exception as e:
        return ToolResult(success=False, output=None, error=str(e))
