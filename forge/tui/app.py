"""
Forge TUI — real terminal UI using prompt_toolkit.
Split panes, syntax highlighting, keybindings, autocomplete.
This is what makes Forge feel like a real tool, not a script.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from ..core.planner import Plan, StepStatus
from ..tools.registry import ToolResult


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
    "phase": "bold cyan",
    "score": "bold green",
})


COMMANDS = [
    "/help", "/tools", "/plan", "/stats", "/project",
    "/clear", "/save", "/sessions", "/model", "/provider",
    "/memory", "/git", "/quit", "/exit",
]


class ForgeApp:
    """
    Interactive terminal application for Forge.
    Rich TUI with proper input handling, keybindings, and display.
    """

    def __init__(self, config):
        self.config = config
        self.console = Console(theme=FORGE_THEME)
        self._history_file = os.path.expanduser("~/.forge/history")
        os.makedirs(os.path.dirname(self._history_file), exist_ok=True)

        # Command completer
        self._completer = WordCompleter(COMMANDS, ignore_case=True)

        # Key bindings
        self._bindings = KeyBindings()

        @self._bindings.add("c-c")
        def _(event):
            """Cancel current input."""
            event.app.exit(exception=KeyboardInterrupt)

        @self._bindings.add("c-d")
        def _(event):
            """Exit on Ctrl+D."""
            event.app.exit(exception=EOFError)

        # Prompt session
        self._session: Optional[PromptSession] = None

    def _create_session(self) -> PromptSession:
        """Create a prompt_toolkit session."""
        return PromptSession(
            history=FileHistory(self._history_file),
            auto_suggest=AutoSuggestFromHistory(),
            completer=self._completer,
            key_bindings=self._bindings,
            multiline=False,
            wrap_lines=True,
        )

    def banner(self) -> None:
        """Show the Forge banner."""
        banner = """
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
        self.console.print(banner)

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

    def show_phase(self, phase) -> None:
        """Show current agent phase."""
        phase_icons = {
            "idle": "⏸️",
            "reasoning": "🧠",
            "planning": "📋",
            "executing": "⚡",
            "verifying": "🔍",
            "recovering": "🔄",
            "summarizing": "📝",
            "done": "✅",
        }
        icon = phase_icons.get(phase.value if hasattr(phase, 'value') else str(phase), "❓")
        name = phase.value if hasattr(phase, 'value') else str(phase)
        self.console.print(f"\n[phase]{icon} {name.title()}...[/]")

    def show_thought(self, thought: str) -> None:
        """Display agent's reasoning."""
        if thought and thought.strip():
            # Truncate long thoughts
            if len(thought) > 300:
                thought = thought[:300] + "..."
            self.console.print(f"[thinking]💭 {thought}[/]")

    def show_action(self, tool_name: str, args: dict) -> None:
        """Show tool execution start."""
        # Format args nicely
        formatted = []
        for k, v in args.items():
            val = str(v)
            if len(val) > 80:
                val = val[:77] + "..."
            formatted.append(f"{k}={val}")
        args_str = ", ".join(formatted)

        self.console.print(f"[tool]⚡ {tool_name}[/]({args_str})")

    def show_observation(self, tool_name: str, result: ToolResult) -> None:
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
                self.console.print(f"[dim]{str(result.output)[:300]}[/]")

    def show_streaming_start(self) -> None:
        """Prepare for streaming output."""
        self.console.print(f"\n[bold white]Forge:[/] ", end="")

    def show_token(self, token: str) -> None:
        """Display a streaming token."""
        self.console.print(token, end="", highlight=False)

    def show_streaming_end(self) -> None:
        """Finish streaming output."""
        self.console.print()

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

        provider_stats = stats.get("provider", {})
        if provider_stats:
            table.add_row("LLM requests", str(provider_stats.get("requests", 0)))
            table.add_row("Total tokens", str(provider_stats.get("total_tokens", 0)))
            table.add_row("Avg latency", f"{provider_stats.get('avg_latency_ms', 0):.0f}ms")

        self.console.print(table)

    def show_project_context(self, context) -> None:
        """Display project context."""
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

    def show_error(self, error: str) -> None:
        """Display an error."""
        self.console.print(f"\n[error]Error:[/] {error}")

    def show_warning(self, warning: str) -> None:
        """Display a warning."""
        self.console.print(f"[warning]⚠️ {warning}[/]")

    def show_success(self, message: str) -> None:
        """Display a success message."""
        self.console.print(f"[success]✅ {message}[/]")

    async def request_approval(self, tool_name: str, args: dict) -> bool:
        """Request user approval for a dangerous tool."""
        self.console.print()
        self.console.print(f"[warning]⚠️ Approval needed: [bold]{tool_name}[/bold][/]")
        for k, v in args.items():
            val = str(v)
            if len(val) > 200:
                val = val[:200] + "..."
            self.console.print(f"  [dim]{k}:[/] {val}")

        try:
            response = self._session.prompt(
                HTML("<ansiyellow>Allow? (y/N): </ansiyellow>"),
            )
            return response.strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def get_input(self) -> Optional[str]:
        """Get user input with proper prompt handling."""
        if not self._session:
            self._session = self._create_session()

        try:
            with patch_stdout():
                return self._session.prompt(
                    HTML("<ansicyan><b>You:</b></ansicyan> "),
                )
        except (EOFError, KeyboardInterrupt):
            return None

    def show_message(self, role: str, content: str) -> None:
        """Display a message."""
        if role == "user":
            self.console.print(f"\n[bold cyan]You:[/] {content}")
        elif role == "assistant":
            self.console.print(f"\n[bold white]Forge:[/]")
            self.console.print(Markdown(content))

    def show_diff(self, diff: str, title: str = "Changes") -> None:
        """Display a diff with syntax highlighting."""
        if not diff.strip():
            return

        self.console.print(f"\n[bold]{title}[/]")
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                self.console.print(f"[green]{line}[/]")
            elif line.startswith("-") and not line.startswith("---"):
                self.console.print(f"[red]{line}[/]")
            elif line.startswith("@@"):
                self.console.print(f"[cyan]{line}[/]")
            else:
                self.console.print(line)

    def show_code(self, code: str, language: str = "python", title: str = "") -> None:
        """Display code with syntax highlighting."""
        if title:
            self.console.print(f"\n[bold]{title}[/]")
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        self.console.print(syntax)

    def clear(self) -> None:
        """Clear the console."""
        self.console.clear()

    def print(self, *args, **kwargs) -> None:
        """Proxy to console.print."""
        self.console.print(*args, **kwargs)


def show_help(console: Console) -> None:
    """Show help information."""
    help_text = """
[bold]🔨 Forge Commands[/]

  /help          Show this help message
  /tools         List available tools
  /project       Show project analysis
  /plan          Show current execution plan
  /stats         Show session statistics
  /memory        Show memory contents
  /git           Show git status
  /sessions      List saved sessions
  /save [id]     Save current session
  /model <name>  Switch LLM model
  /clear         Clear the screen
  /quit          Exit Forge

[bold]Keyboard Shortcuts:[/]
  Ctrl+C         Cancel current operation
  Ctrl+D         Exit Forge
  Tab            Auto-complete commands
  ↑/↓            Browse command history

[bold]Tips:[/]
  • Describe what you want in natural language
  • Forge plans, executes, and verifies automatically
  • It reads files before editing them
  • It runs tests after making changes
  • It self-corrects when things fail
  • It learns your preferences over time
"""
    console.print(help_text)
