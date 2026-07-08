"""
Terminal UI — beautiful, informative, fast.
Rich-powered display with syntax highlighting and real-time feedback.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from ..tools.registry import ToolResult
from ..core.planner import Plan, StepStatus


# Forge theme
FORGE_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "tool": "bold magenta",
    "file": "bold blue",
    "path": "dim cyan",
    "thinking": "dim white",
    "agent": "bold white",
    "banner": "bold yellow",
})


class Display:
    """Rich terminal UI for Forge."""

    def __init__(self, theme: str = "forge_dark"):
        self.console = Console(theme=FORGE_THEME)
        self._live: Optional[Live] = None
        self._thinking = False

    def banner(self) -> None:
        """Show the Forge banner."""
        banner_text = """
[bold yellow]
  ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  █████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
  ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
  ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝[/]
[dim]  The Agentic Coding Tool That Actually Works[/]
[dim]  100% local • Zero cloud • Your code stays yours[/]
"""
        self.console.print(banner_text)

    def show_info(self, provider: str, model: str, project: str = "") -> None:
        """Show session info."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim")
        table.add_column("Value", style="bold")
        table.add_row("Provider", provider)
        table.add_row("Model", model)
        if project:
            table.add_row("Project", project)
        self.console.print(table)
        self.console.print()

    def show_message(self, role: str, content: str) -> None:
        """Display a message."""
        if role == "user":
            self.console.print(f"\n[bold cyan]You:[/] ", end="")
            self.console.print(content)
        elif role == "assistant":
            self.console.print(f"\n[bold white]Forge:[/]")
            # Render markdown
            md = Markdown(content)
            self.console.print(md)
        elif role == "system":
            self.console.print(f"[dim]{content}[/]")

    def show_streaming_start(self) -> None:
        """Prepare for streaming output."""
        self.console.print(f"\n[bold white]Forge:[/]")

    def show_token(self, token: str) -> None:
        """Display a streaming token."""
        self.console.print(token, end="", highlight=False)

    def show_streaming_end(self) -> None:
        """Finish streaming output."""
        self.console.print()  # Newline after streaming

    def show_tool_start(self, tool_name: str, args: dict) -> None:
        """Show tool execution start."""
        # Format args nicely
        args_str = ", ".join(f"{k}={self._truncate(str(v), 80)}" for k, v in args.items())
        self.console.print(f"\n[tool]⚡ {tool_name}[/]({args_str})")

    def show_tool_end(self, tool_name: str, result: ToolResult) -> None:
        """Show tool execution result."""
        if result.success:
            output = str(result.output)
            if len(output) > 500:
                output = output[:250] + f"\n... ({len(str(result.output)) - 500} chars)" + f"\n{output[-250:]}"
            self.console.print(f"[success]✓[/] ", end="")
            self.console.print(output, highlight=False)
        else:
            self.console.print(f"[error]✗ {result.error}[/]")
            if result.output:
                self.console.print(f"[dim]{str(result.output)[:500]}[/]")

    def show_plan(self, plan: Plan) -> None:
        """Display an execution plan."""
        table = Table(
            title=f"📋 {plan.goal}",
            show_header=True,
            header_style="bold",
            title_style="bold yellow",
        )
        table.add_column("", width=3)
        table.add_column("Step", style="bold")
        table.add_column("Description")
        table.add_column("Status", justify="center")

        status_styles = {
            StepStatus.PENDING: ("⬜", "dim"),
            StepStatus.IN_PROGRESS: ("🔄", "yellow"),
            StepStatus.COMPLETED: ("✅", "green"),
            StepStatus.FAILED: ("❌", "red"),
            StepStatus.SKIPPED: ("⏭️", "dim"),
        }

        for step in plan.steps:
            icon, style = status_styles.get(step.status, ("⬜", "dim"))
            table.add_row(
                icon,
                str(step.id),
                step.description,
                f"[{style}]{step.status.value}[/]",
            )

        self.console.print(table)
        self.console.print(f"[dim]Progress: {plan.progress:.0%}[/]")

    def show_error(self, error: str) -> None:
        """Display an error."""
        self.console.print(f"\n[error]Error:[/] {error}")

    def show_warning(self, warning: str) -> None:
        """Display a warning."""
        self.console.print(f"[warning]⚠️ {warning}[/]")

    def show_success(self, message: str) -> None:
        """Display a success message."""
        self.console.print(f"[success]✅ {message}[/]")

    def show_stats(self, stats: dict) -> None:
        """Display execution statistics."""
        table = Table(title="📊 Session Stats", show_header=False, box=None)
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")
        table.add_row("Iterations", str(stats.get("iterations", 0)))
        table.add_row("Tool calls", str(stats.get("tool_calls", 0)))
        table.add_row("Errors", str(stats.get("errors", 0)))
        table.add_row("Files modified", str(stats.get("files_modified", 0)))
        table.add_row("Time", f"{stats.get('elapsed_s', 0):.1f}s")

        provider_stats = stats.get("provider_stats", {})
        if provider_stats:
            table.add_row("LLM requests", str(provider_stats.get("requests", 0)))
            table.add_row("Total tokens", str(provider_stats.get("total_tokens", 0)))
            table.add_row("Avg latency", f"{provider_stats.get('avg_latency_ms', 0):.0f}ms")

        self.console.print(table)

    def show_project_context(self, context) -> None:
        """Display project context information."""
        tree = Tree("📁 Project")
        tree.add(f"[bold]{context.root.name}[/]")

        if context.git_branch:
            tree.add(f"🌿 Branch: {context.git_branch}")

        if context.languages:
            lang_tree = tree.add("📝 Languages")
            for lang, count in sorted(context.languages.items(), key=lambda x: -x[1])[:5]:
                lang_tree.add(f"{lang}: {count} files")

        if context.framework:
            tree.add(f"🔧 Framework: {context.framework}")
        if context.package_manager:
            tree.add(f"📦 Package: {context.package_manager}")
        if context.has_tests:
            tree.add(f"🧪 Tests: {context.test_framework or 'yes'}")

        self.console.print(tree)

    async def request_approval(self, tool_name: str, args: dict) -> bool:
        """Request user approval for a dangerous tool."""
        self.console.print()
        self.console.print(f"[warning]⚠️ Approval needed for: [bold]{tool_name}[/bold][/]")
        for k, v in args.items():
            val_str = str(v)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            self.console.print(f"  [dim]{k}:[/] {val_str}")

        try:
            return Confirm.ask("Allow this action?", default=False, console=self.console)
        except (EOFError, KeyboardInterrupt):
            return False

    def get_input(self, prompt: str = "You") -> Optional[str]:
        """Get user input with a nice prompt."""
        try:
            self.console.print()
            return self.console.input(f"[bold cyan]{prompt}:[/] ")
        except (EOFError, KeyboardInterrupt):
            return None

    def clear(self) -> None:
        """Clear the console."""
        self.console.clear()

    @staticmethod
    def _truncate(s: str, max_len: int) -> str:
        if len(s) <= max_len:
            return s
        return s[:max_len - 3] + "..."
