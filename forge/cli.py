"""
Forge CLI — the main entry point.
Uses ReAct agent and real TUI.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import click

from .config import Config
from .core.intelligent_agent import IntelligentAgent, Phase
from .core.context import ProjectContext
from .core.memory import SessionMemory
from .llm import get_provider
from .session import SessionManager
from .tools.registry import registry as tool_registry
from .tui.app import ForgeApp, show_help

# Load all built-in tools
from .tools import builtin  # noqa: F401
from .tools import advanced  # noqa: F401
from .tools import graph_tools  # noqa: F401
from .tools import backlinks  # noqa: F401


@click.group(invoke_without_command=True)
@click.option("--model", "-m", default=None, help="LLM model to use")
@click.option("--provider", "-p", default=None, help="LLM provider (ollama, openai, anthropic)")
@click.option("--api-base", default=None, help="API base URL")
@click.option("--api-key", default=None, help="API key (for cloud providers)")
@click.option("--temperature", "-t", default=None, type=float, help="Temperature (0.0-1.0)")
@click.option("--auto-approve", is_flag=True, help="Auto-approve all tool calls")
@click.option("--no-stream", is_flag=True, help="Disable streaming")
@click.option("--session", "-s", default=None, help="Session ID to resume")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Config file path")
@click.option("--theme", default=None, help="TUI theme")
@click.version_option(version="0.2.0", prog_name="forge")
@click.pass_context
def main(
    ctx: click.Context,
    model: Optional[str],
    provider: Optional[str],
    api_base: Optional[str],
    api_key: Optional[str],
    temperature: Optional[float],
    auto_approve: bool,
    no_stream: bool,
    session: Optional[str],
    config_path: Optional[str],
    theme: Optional[str],
) -> None:
    """🔨 Forge — The Agentic Coding Tool That Actually Works

    Run without a command to start interactive mode.
    Use 'forge run <task>' for one-shot execution.
    """
    config = Config.load(Path(config_path) if config_path else None)

    if model:
        config.override("model", model)
    if provider:
        config.override("provider", provider)
    if api_base:
        config.override("api_base", api_base)
    if api_key:
        config.override("api_key", api_key)
    if temperature is not None:
        config.override("temperature", temperature)
    if auto_approve:
        config.auto_approve = True
    if theme:
        config.theme = theme

    config.ensure_dirs()

    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["no_stream"] = no_stream
    ctx.obj["session_id"] = session

    if ctx.invoked_subcommand is None:
        asyncio.run(interactive_mode(config, no_stream, session))


@main.command()
@click.argument("task", nargs=-1, required=True)
@click.pass_context
def run(ctx: click.Context, task: tuple) -> None:
    """Execute a one-shot task and exit."""
    config = ctx.obj["config"]
    no_stream = ctx.obj["no_stream"]
    task_text = " ".join(task)
    asyncio.run(one_shot_mode(config, task_text, no_stream))


@main.command()
@click.pass_context
def models(ctx: click.Context) -> None:
    """List available models."""
    config = ctx.obj["config"]

    async def _list():
        provider = get_provider(config)
        try:
            model_list = await provider.available_models()
            console = ForgeApp(config).console
            console.print("\n[bold]Available models:[/]")
            for m in model_list:
                marker = " ← current" if m == config.model else ""
                console.print(f"  • {m}[dim]{marker}[/]")
            console.print()
        finally:
            await provider.close()

    asyncio.run(_list())


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show Forge status."""
    config = ctx.obj["config"]
    app = ForgeApp(config)

    async def _status():
        provider = get_provider(config)
        from rich.table import Table

        app.console.print("\n[bold]🔨 Forge Status[/]\n")

        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column("Key", style="dim")
        t.add_column("Value", style="bold")

        info = [
            ("Provider", config.provider),
            ("Model", config.model),
            ("API Base", config.api_base),
            ("Temperature", str(config.temperature)),
            ("Max Iterations", str(config.max_iterations)),
            ("Auto Approve", str(config.auto_approve)),
            ("Tools available", str(len(tool_registry.tool_names))),
        ]
        for k, v in info:
            t.add_row(k, v)

        healthy = await provider.health_check()
        status_str = "[green]✓ Connected[/]" if healthy else "[red]✗ Disconnected[/]"
        t.add_row("Status", status_str)

        app.console.print(t)
        app.console.print(f"\n[dim]Provider stats: {provider.stats}[/]")
        await provider.close()

    asyncio.run(_status())


@main.command()
@click.pass_context
def tools(ctx: click.Context) -> None:
    """List available tools."""
    config = ctx.obj["config"]
    app = ForgeApp(config)

    from rich.table import Table
    t = Table(show_header=True, header_style="bold")
    t.add_column("Name", style="bold")
    t.add_column("Category")
    t.add_column("Description")
    t.add_column("Flags", justify="center")

    for name in tool_registry.tool_names:
        tool_obj = tool_registry.get(name)
        if tool_obj:
            flags = []
            if tool_obj.dangerous:
                flags.append("⚠️")
            t.add_row(
                name,
                tool_obj.category,
                tool_obj.description[:80],
                " ".join(flags) if flags else "",
            )

    app.console.print(t)


@main.command()
@click.pass_context
def sessions(ctx: click.Context) -> None:
    """List saved sessions."""
    config = ctx.obj["config"]
    from .config import FORGE_HOME
    manager = SessionManager(FORGE_HOME / "sessions")
    app = ForgeApp(config)

    session_list = manager.list_sessions()
    if not session_list:
        app.console.print("[dim]No saved sessions.[/]")
        return

    from rich.table import Table
    import datetime

    t = Table(title="📝 Sessions", show_header=True, header_style="bold")
    t.add_column("ID")
    t.add_column("Messages", justify="right")
    t.add_column("Files", justify="right")
    t.add_column("Last Active")

    for s in session_list:
        ts = datetime.datetime.fromtimestamp(s["updated_at"]).strftime("%Y-%m-%d %H:%M")
        t.add_row(s["id"], str(s["messages"]), str(s["files"]), ts)

    app.console.print(t)


async def interactive_mode(
    config: Config,
    no_stream: bool = False,
    session_id: Optional[str] = None,
) -> None:
    """Run Forge in interactive mode with full TUI."""
    app = ForgeApp(config)
    app.banner()

    # Initialize provider
    try:
        provider = get_provider(config)
    except Exception as e:
        app.show_error(f"Failed to initialize LLM provider: {e}")
        app.console.print("[dim]Make sure Ollama is running: ollama serve[/]")
        return

    # Health check
    healthy = await provider.health_check()
    if not healthy:
        app.show_warning(f"Cannot connect to {config.provider} at {config.api_base}")
        app.console.print("[dim]Make sure the provider is running and accessible.[/]")
        try:
            response = app._session.prompt("Continue anyway? (y/N): ") if app._session else input("Continue anyway? (y/N): ")
            if response.strip().lower() not in ("y", "yes"):
                return
        except (EOFError, KeyboardInterrupt):
            return

    # Scan project
    app.console.print("[dim]Scanning project...[/]")
    context = ProjectContext()
    context.scan()

    app.show_info(config.provider, config.model, context.root.name)

    # Session management
    from .config import FORGE_HOME
    session_manager = SessionManager(FORGE_HOME / "sessions")
    memory = SessionMemory(FORGE_HOME / "memory")

    session = session_manager.load(session_id) if session_id else session_manager.create()

    # Create agent
    agent = IntelligentAgent(
        provider=provider,
        config=config,
        tools=tool_registry,
        context=context,
        display=app,
    )

    # Wire callbacks
    agent.on_phase(lambda phase: app.show_phase(phase))
    agent.on_action(lambda name, args: app.show_action(name, args))
    agent.on_observation(lambda name, result: app.show_observation(name, result))
    if not no_stream:
        agent.on_token(lambda token: app.show_token(token))

    # Help hint
    app.console.print("[dim]Type your task. Commands: /help, /plan, /stats, /clear, /quit[/]")

    # Main loop
    while True:
        try:
            user_input = app.get_input()
        except (EOFError, KeyboardInterrupt):
            app.console.print("\n[dim]Goodbye![/]")
            break

        if user_input is None:
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            handled = await _handle_command(user_input, app, agent, session, session_manager, memory, config)
            if handled == "quit":
                break
            continue

        # Execute task
        session.add_message("user", user_input)

        if not no_stream:
            app.show_streaming_start()

        try:
            response = await agent.run_task(user_input, stream=not no_stream)
        except Exception as e:
            app.show_error(f"Agent error: {type(e).__name__}: {str(e)}")
            response = f"I encountered an error: {str(e)}"

        if not no_stream:
            app.show_streaming_end()
        elif response:
            app.console.print(f"\n[bold white]Forge:[/]")
            app.console.print(Markdown(response))

        session.add_message("assistant", response)
        session.files_modified = list(set(agent.run.files_modified)) if agent.run else []
        session_manager.save(session)

    # Final stats
    app.console.print()
    if agent.run:
        app.show_stats(agent.stats)

    await provider.close()


async def one_shot_mode(config: Config, task: str, no_stream: bool = False) -> None:
    """Execute a single task and exit."""
    app = ForgeApp(config)

    try:
        provider = get_provider(config)
    except Exception as e:
        app.show_error(f"Failed to initialize provider: {e}")
        sys.exit(1)

    context = ProjectContext()
    context.scan()
    app.show_info(config.provider, config.model, context.root.name)

    agent = IntelligentAgent(
        provider=provider,
        config=config,
        tools=tool_registry,
        context=context,
        display=app,
    )

    agent.on_phase(lambda phase: app.show_phase(phase))
    agent.on_action(lambda name, args: app.show_action(name, args))
    agent.on_observation(lambda name, result: app.show_observation(name, result))
    if not no_stream:
        agent.on_token(lambda token: app.show_token(token))

    if not no_stream:
        app.show_streaming_start()

    try:
        response = await agent.run_task(task, stream=not no_stream)
    except Exception as e:
        app.show_error(f"Error: {type(e).__name__}: {str(e)}")
        response = ""

    if not no_stream:
        app.show_streaming_end()
    elif response:
        app.console.print(response)

    app.console.print()
    app.show_stats(agent.stats)
    await provider.close()


async def _handle_command(
    cmd: str, app: ForgeApp, agent: IntelligentAgent,
    session, session_manager, memory, config,
) -> str:
    """Handle a command. Returns 'quit' to exit."""
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        return "quit"

    elif command == "/help":
        show_help(app.console)

    elif command == "/clear":
        app.clear()
        app.banner()

    elif command == "/stats":
        if agent.run:
            app.show_stats(agent.stats)
        else:
            app.console.print("[dim]No active run.[/]")

    elif command == "/plan":
        if agent.run and agent.run.plan:
            app.show_plan(agent.run.plan)
        else:
            app.console.print("[dim]No active plan.[/]")

    elif command == "/tools":
        app.console.print(tool_registry.summary())

    elif command == "/project":
        app.show_project_context(agent.context)

    elif command == "/memory":
        stats = memory.stats()
        app.console.print(f"\n[bold]🧠 Memory[/] ({stats['total']} entries)")
        if stats['by_kind']:
            for kind, count in stats['by_kind'].items():
                app.console.print(f"  {kind}: {count}")
        # Show recent memories
        results = memory.search("", limit=5)
        if results:
            app.console.print("\n[dim]Recent memories:[/]")
            for m in results:
                app.console.print(f"  [{m.kind}] {m.key}: {m.content[:100]}")

    elif command == "/git":
        from .core.git_workflow import GitWorkflow
        gw = GitWorkflow()
        if await gw.is_git_repo():
            status = await gw.status()
            app.console.print(f"\n{status.summary()}")
        else:
            app.console.print("[dim]Not a git repository.[/]")

    elif command == "/sessions":
        for s in session_manager.list_sessions():
            app.console.print(f"  {s['id']} ({s['messages']} msgs)")

    elif command == "/save":
        sid = args or session.id
        session.id = sid
        session_manager.save(session)
        app.show_success(f"Session saved: {sid}")

    elif command == "/model":
        if args:
            config.override("model", args)
            app.show_success(f"Model changed to: {args}")
        else:
            app.console.print(f"Current model: {config.model}")

    elif command == "/provider":
        if args:
            config.override("provider", args)
            app.show_success(f"Provider changed to: {args}. Restart to take effect.")
        else:
            app.console.print(f"Current provider: {config.provider}")

    else:
        app.show_warning(f"Unknown command: {command}. Type /help for available commands.")

    return "ok"


if __name__ == "__main__":
    main()
