"""
Intelligent Agent — graph-aware, pattern-learning, self-correcting.
This is the REAL brain. Not just a tool-calling loop.
It thinks in terms of relationships, impact, and consequences.

Every action goes through:
1. UNDERSTAND — parse the task, find relevant code via graph
2. ANALYZE — impact analysis, dependency check, risk assessment
3. PLAN — create a plan informed by the graph
4. EXECUTE — make changes with full awareness of consequences
5. VERIFY — run tests, check for breakage, validate
6. LEARN — remember what worked, update patterns
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

from ..llm.base import LLMMessage, LLMProvider, StreamChunk, ToolDefinition
from ..tools.registry import ToolRegistry, ToolResult
from .context import ProjectContext
from .context_window import ConversationContext
from .error_recovery import ErrorRecoveryEngine
from .knowledge_graph import KnowledgeGraph, ImpactAnalysis
from .memory import SessionMemory
from .planner import Plan, Planner, StepStatus


class Phase(str, Enum):
    UNDERSTAND = "understand"
    ANALYZE = "analyze"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    RECOVER = "recover"
    LEARN = "learn"
    DONE = "done"


@dataclass
class AgentStep:
    phase: Phase
    thought: str = ""
    action: str = ""
    args: dict = field(default_factory=dict)
    result: Optional[ToolResult] = None
    impact: Optional[ImpactAnalysis] = None
    duration_ms: float = 0.0


@dataclass
class AgentRun:
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0.0
    files_modified: list[str] = field(default_factory=list)
    tests_run: int = 0
    tests_passed: int = 0
    errors_recovered: int = 0
    final_response: str = ""
    success: bool = False

    @property
    def elapsed(self) -> float:
        end = self.end_time or time.monotonic()
        return end - self.start_time


INTELLIGENT_PROMPT = """You are Forge, the world's most intelligent agentic coding assistant. You run 100% locally.

## Your Brain: The Knowledge Graph

You have something no other coding tool has: a **knowledge graph** of the entire codebase.
Every function, class, file, and their relationships are mapped. You can:
- See who calls any function (and who calls those callers)
- Analyze the impact of changing ANYTHING before you change it
- Find related code (callers, callees, tests, imports, same-class)
- Detect anti-patterns (god objects, circular deps, dead code)
- Trace call chains through the entire codebase

**USE YOUR BRAIN.** Before modifying code:
1. `graph_impact` — what breaks if I change this?
2. `graph_related` — what else should I look at?
3. `graph_who_calls` — who depends on this?

## How You Think (Graph-Aware ReAct)

For every task:

### Phase 1: UNDERSTAND
- Read the task carefully
- Use `semantic_search` or `find_symbol` to locate relevant code
- Read the files involved
- Understand the existing patterns and conventions

### Phase 2: ANALYZE (THE KEY DIFFERENCE)
- Use `graph_impact` on EVERY symbol you're about to change
- Use `graph_related` to find all connected code
- Check `graph_deps` for import dependencies
- Use `recall` to check for relevant memories/preferences
- Assess risk: low/medium/high/critical

### Phase 3: PLAN
- Create a plan informed by the impact analysis
- If high impact: be extra careful, consider breaking into smaller steps
- If tests exist: plan to run them after changes
- If no tests: consider writing tests first

### Phase 4: EXECUTE
- Make surgical changes (edit, not write)
- After EACH file change, note what changed
- Batch related changes

### Phase 5: VERIFY
- Run tests if they exist
- Check for syntax errors
- Verify the change achieves the goal
- If tests fail → go to RECOVER

### Phase 6: RECOVER (if needed)
- Parse errors with `analyze_errors`
- Understand WHY it failed
- Fix the root cause, not the symptom
- Re-verify

### Phase 7: LEARN
- `remember` any preferences or patterns discovered
- Note what worked for future reference

## Tool Usage Priority

For code understanding (use in this order):
1. `graph_impact` / `graph_related` / `graph_who_calls` — relationship awareness
2. `find_symbol` / `get_function` — AST-aware code lookup
3. `semantic_search` — meaning-based search
4. `search` — keyword search (ripgrep)
5. `read` — read file contents

For code changes:
1. `edit` — surgical text replacement (PREFERRED)
2. `multi_edit` — multiple edits in one file
3. `write` — only for new files or complete rewrites
4. `create` — new files

For verification:
1. `test` — run project tests
2. `shell` — run specific commands
3. `analyze_errors` — parse error output

## Error Recovery

When something fails:
1. `analyze_errors` — parse the error output
2. Read the error message — it usually contains the fix
3. `graph_impact` — check if the error is from a dependency
4. Fix the ROOT CAUSE, not the symptom
5. Re-verify

## Code Quality Rules

- Read before editing — ALWAYS
- Follow existing conventions (indentation, naming, patterns)
- Type hints where the language supports them
- Error handling for all external calls
- Tests for new functionality
- Update docs when changing behavior
- Keep functions under 50 lines
- Keep classes under 200 lines

## Response Style

- Be direct and concise
- Show what you're doing and why
- After completing: summarize changes and remaining work
- If something is risky: say so and explain the risk"""


class IntelligentAgent:
    """
    The REAL brain of Forge. Graph-aware, pattern-learning, self-correcting.

    Key differences from a basic agent:
    1. Every code change is preceded by impact analysis
    2. The knowledge graph informs all decisions
    3. It learns from past sessions
    4. It self-corrects with error analysis
    5. It verifies changes with tests
    """

    def __init__(
        self,
        provider: LLMProvider,
        config,
        tools: ToolRegistry,
        context: ProjectContext,
        display=None,
    ):
        self.provider = provider
        self.config = config
        self.tools = tools
        self.context = context
        self.display = display
        self.planner = Planner(provider, config)
        self.error_engine = ErrorRecoveryEngine()
        self.conv = ConversationContext(max_tokens=config.max_context_tokens)
        self.graph: Optional[KnowledgeGraph] = None
        self.memory: Optional[SessionMemory] = None
        self.run: Optional[AgentRun] = None

        # Callbacks
        self._on_phase: Optional[Callable] = None
        self._on_thought: Optional[Callable] = None
        self._on_action: Optional[Callable] = None
        self._on_observation: Optional[Callable] = None
        self._on_token: Optional[Callable] = None
        self._on_impact: Optional[Callable] = None

        # Initialize memory
        try:
            from ..config import FORGE_HOME
            self.memory = SessionMemory(FORGE_HOME / "memory")
        except Exception:
            pass

    def on_phase(self, cb): self._on_phase = cb
    def on_thought(self, cb): self._on_thought = cb
    def on_action(self, cb): self._on_action = cb
    def on_observation(self, cb): self._on_observation = cb
    def on_token(self, cb): self._on_token = cb
    def on_impact(self, cb): self._on_impact = cb

    def _set_phase(self, phase: Phase):
        if self._on_phase:
            self._on_phase(phase)

    async def _build_graph(self):
        """Build the knowledge graph (lazy, on first use)."""
        if self.graph is None:
            self.graph = KnowledgeGraph()
            try:
                self.graph.build_from_directory(".")
            except Exception:
                pass

    async def run_task(self, task: str, stream: bool = True) -> str:
        """Execute a task with full graph awareness."""
        self.run = AgentRun(task=task)

        # Build graph
        self._set_phase(Phase.UNDERSTAND)
        await self._build_graph()

        # Build system prompt
        system = self._build_system()

        # Initialize conversation
        self.conv.set_system(system)
        self.conv.add_user_message(task)

        # Pre-flight: graph analysis of the task
        graph_context = await self._preflight_analysis(task)
        if graph_context:
            self.conv.add_user_message(f"[Graph Analysis]\n{graph_context}")

        # Add memory context
        if self.memory:
            mem_context = self.memory.get_context_summary(task)
            if mem_context:
                self.conv.add_user_message(f"[Memory]\n{mem_context}")

        # Main loop
        iteration = 0
        consecutive_errors = 0

        while iteration < self.config.max_iterations:
            iteration += 1

            self._set_phase(Phase.EXECUTE)

            try:
                response = await self._get_response(stream)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    self.run.final_response = f"Repeated LLM errors: {e}"
                    break
                self.conv.add_user_message(
                    f"[System Error] {e}. Adjust and retry."
                )
                continue

            if response.has_tool_calls:
                self.conv.add_assistant_message(response.content or "")

                # Execute tools with impact awareness
                should_continue = await self._execute_tools(response.tool_calls)
                if not should_continue:
                    break

                # Auto-verify after changes
                if self.run.files_modified:
                    self._set_phase(Phase.VERIFY)
                    await self._auto_verify()

            else:
                self.run.final_response = response.content
                self.run.success = True
                break

        # Generate summary if needed
        if not self.run.final_response:
            self._set_phase(Phase.LEARN)
            self.run.final_response = await self._generate_summary()

        # Learn from this run
        await self._learn_from_run()

        self.run.end_time = time.monotonic()
        self._set_phase(Phase.DONE)
        return self.run.final_response

    def _build_system(self) -> str:
        """Build system prompt with all context."""
        system = INTELLIGENT_PROMPT

        # Project context
        summary = self.context.summary()
        if summary:
            system += f"\n\n## Current Project\n{summary}"

        # Graph stats
        if self.graph:
            stats = self.graph.stats
            system += f"\n\n## Knowledge Graph\n"
            system += f"Nodes: {stats['total_nodes']}, Edges: {stats['total_edges']}\n"
            system += f"Files: {stats['files']}, Symbols: {stats['unique_names']}"

        # User preferences
        if self.memory:
            prefs = self.memory.get_preferences()
            if prefs:
                system += "\n\n## User Preferences\n"
                for k, v in prefs.items():
                    system += f"- {k}: {v}\n"

        # Available tools
        system += "\n\n## Available Tools\n"
        for tool in self.tools.definitions:
            func = tool.to_dict()["function"]
            system += f"- {func['name']}: {func['description'][:100]}\n"

        return system

    async def _preflight_analysis(self, task: str) -> str:
        """Analyze the task using the knowledge graph before starting."""
        if not self.graph:
            return ""

        parts = []

        # Extract potential symbol names from the task
        import re
        # Look for function/class-like names
        names = re.findall(r'\b([a-z_][a-z0-9_]+|[A-Z][a-zA-Z0-9]+)\b', task)

        for name in names[:5]:
            if len(name) < 3:
                continue

            # Check if it exists in the graph
            related = self.graph.find_related(name)
            if any(related.values()):
                parts.append(f"Symbol '{name}' found in codebase:")
                if related["callers"]:
                    parts.append(f"  Called by: {', '.join(related['callers'][:3])}")
                if related["tests"]:
                    parts.append(f"  Tests: {', '.join(related['tests'][:3])}")
                if related["imports"]:
                    parts.append(f"  Imports: {', '.join(related['imports'][:3])}")

        return "\n".join(parts) if parts else ""

    async def _get_response(self, stream: bool):
        """Get LLM response."""
        messages = [LLMMessage(role=m["role"], content=m["content"]) for m in self.conv.to_messages()]

        if stream:
            return await self._stream(messages)
        else:
            return await self.provider.chat(
                messages=messages,
                tools=self.tools.definitions,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

    async def _stream(self, messages):
        """Stream response with token callbacks."""
        from ..llm.base import LLMResponse

        full = ""
        tool_calls = None
        finish = None

        async for chunk in self.provider.stream_chat(
            messages=messages,
            tools=self.tools.definitions,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        ):
            if chunk.delta:
                full += chunk.delta
                if self._on_token:
                    self._on_token(chunk.delta)

            if chunk.tool_calls:
                if tool_calls is None:
                    tool_calls = []
                for tc in chunk.tool_calls:
                    idx = tc.get("index", len(tool_calls))
                    while len(tool_calls) <= idx:
                        tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if "id" in tc and tc["id"]:
                        tool_calls[idx]["id"] = tc["id"]
                    func = tc.get("function", {})
                    if "name" in func and func["name"]:
                        tool_calls[idx]["function"]["name"] = func["name"]
                    if "arguments" in func:
                        tool_calls[idx]["function"]["arguments"] += func["arguments"]

            if chunk.finish_reason:
                finish = chunk.finish_reason
            if chunk.done:
                break

        return LLMResponse(content=full, tool_calls=tool_calls, finish_reason=finish, model=self.config.model)

    async def _execute_tools(self, tool_calls: list[dict]) -> bool:
        """Execute tools with graph-aware impact analysis."""
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            step = AgentStep(phase=Phase.EXECUTE, action=name, args=args)

            # GRAPH-AWARE: Analyze impact before modifying code
            if name in ("edit", "write", "multi_edit") and self.graph:
                filepath = args.get("path", "")
                if filepath:
                    # Find symbols in the file
                    file_nodes = self.graph._file_nodes.get(filepath, [])
                    for node_id in file_nodes[:3]:
                        node = self.graph.nodes.get(node_id)
                        if node and node.kind.value in ("function", "class", "method"):
                            impact = self.graph.analyze_impact(node.name)
                            if impact.risk_level in ("high", "critical"):
                                step.impact = impact
                                if self._on_impact:
                                    self._on_impact(impact)
                                # Inject impact analysis into context
                                self.conv.add_user_message(
                                    f"[Impact Warning] Changing {filepath} affects:\n"
                                    f"{impact.summary()}\n"
                                    f"Proceed with caution."
                                )
                                break

            # Notify
            if self._on_action:
                self._on_action(name, args)

            # Check approval
            tool_obj = self.tools.get(name)
            if tool_obj and tool_obj.dangerous and self.config.confirm_destructive:
                if not self.config.auto_approve and self.display:
                    approved = await self.display.request_approval(name, args)
                    if not approved:
                        result = ToolResult(success=False, output=None, error="User declined")
                        step.result = result
                        self.run.steps.append(step)
                        self._add_tool_result(name, result)
                        continue

            # Execute
            start = time.monotonic()
            result = await self.tools.execute(name, args)
            step.duration_ms = (time.monotonic() - start) * 1000
            step.result = result

            if result.artifacts:
                self.run.files_modified.extend(result.artifacts)

            if self._on_observation:
                self._on_observation(name, result)

            self._add_tool_result(name, result)
            self.run.steps.append(step)

            # Track errors for recovery
            if not result.success and result.error:
                self.run.errors_recovered += 1

        return True

    def _add_tool_result(self, name: str, result: ToolResult):
        output = result.to_string()
        if len(output) > 8000:
            output = output[:4000] + f"\n... ({len(output) - 8000} chars truncated) ...\n" + output[-4000:]
        self.conv.add_tool_result(name, output)

    async def _auto_verify(self):
        """Automatically verify changes by running tests."""
        if not self.run.files_modified:
            return

        # Check if there are tests
        if not self.context.has_tests:
            return

        # Run tests
        self.conv.add_user_message(
            "[Auto-Verify] Changes were made. Running tests to verify nothing is broken..."
        )

        result = await self.tools.execute("test", {"verbose": True})
        self.run.tests_run += 1

        if result.success:
            self.run.tests_passed += 1
            self.conv.add_tool_result("test (auto-verify)", result)
        else:
            # Tests failed — trigger recovery
            self._set_phase(Phase.RECOVER)
            self.conv.add_user_message(
                f"[Auto-Verify FAILED] Tests failed after changes.\n"
                f"Error: {result.error}\n"
                f"Output: {str(result.output)[:2000]}\n\n"
                f"Analyze the failure and fix the root cause."
            )

            # Parse errors
            if result.output:
                analysis = self.error_engine.analyze(str(result.output))
                if analysis.fix_strategy:
                    self.conv.add_user_message(
                        f"[Error Analysis]\n{analysis.summary()}\n"
                        f"Fix strategy:\n{analysis.fix_strategy}"
                    )

    async def _generate_summary(self) -> str:
        """Generate a summary of what was done."""
        self.conv.add_user_message(
            "[System] Summarize what was accomplished, files changed, and any remaining work."
        )
        messages = [LLMMessage(role=m["role"], content=m["content"]) for m in self.conv.to_messages()]
        resp = await self.provider.chat(messages=messages, temperature=0.3, max_tokens=2048)
        return resp.content

    async def _learn_from_run(self):
        """Learn from this run for future reference."""
        if not self.memory or not self.run:
            return

        # Learn file patterns
        if self.run.files_modified:
            self.memory.remember(
                f"run:{int(time.time())}",
                f"Task: {self.run.task[:100]}. Files: {', '.join(self.run.files_modified[:5])}. "
                f"Success: {self.run.success}. Time: {self.run.elapsed:.1f}s",
                kind="pattern",
            )

    async def chat(self, message: str, stream: bool = True) -> str:
        """Continue conversation."""
        self.conv.add_user_message(message)

        try:
            response = await self._get_response(stream)
        except Exception as e:
            return f"Error: {e}"

        self.conv.add_assistant_message(response.content or "")

        if response.has_tool_calls:
            await self._execute_tools(response.tool_calls)

        return response.content or ""

    @property
    def stats(self) -> dict:
        return {
            "iterations": len(self.run.steps) if self.run else 0,
            "tool_calls": sum(1 for s in (self.run.steps if self.run else []) if s.action),
            "files_modified": len(set(self.run.files_modified)) if self.run else 0,
            "tests_run": self.run.tests_run if self.run else 0,
            "tests_passed": self.run.tests_passed if self.run else 0,
            "errors_recovered": self.run.errors_recovered if self.run else 0,
            "elapsed_s": round(self.run.elapsed, 2) if self.run else 0,
            "provider": self.provider.stats,
            "graph_nodes": self.graph.stats["total_nodes"] if self.graph else 0,
            "graph_edges": self.graph.stats["total_edges"] if self.graph else 0,
        }
