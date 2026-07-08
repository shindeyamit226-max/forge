"""
ReAct Agent — Reasoning + Acting loop.
The core intelligence: thinks, acts, observes, self-corrects.
This is what separates a real agent from a wrapper around an API.

Architecture:
1. REASON — analyze the situation, decide what to do
2. ACT — select and execute a tool
3. OBSERVE — process the result
4. REFLECT — evaluate progress, decide next step or finish
5. SELF-CORRECT — if something failed, analyze why and adapt
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
from .error_recovery import ErrorRecoveryEngine, ErrorAnalysis
from .planner import Plan, Planner, StepStatus


class AgentPhase(str, Enum):
    """Current phase of the agent."""
    IDLE = "idle"
    REASONING = "reasoning"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    SUMMARIZING = "summarizing"
    DONE = "done"


@dataclass
class AgentStep:
    """A single step in the agent's execution."""
    phase: AgentPhase
    thought: str = ""
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    tool_result: Optional[ToolResult] = None
    duration_ms: float = 0.0
    tokens_used: int = 0
    error: Optional[str] = None
    reflection: str = ""


@dataclass
class AgentRun:
    """Complete record of an agent run."""
    task: str
    steps: list[AgentStep] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0.0
    total_tokens: int = 0
    total_tool_calls: int = 0
    total_errors: int = 0
    files_modified: list[str] = field(default_factory=list)
    plan: Optional[Plan] = None
    final_response: str = ""
    success: bool = False

    @property
    def elapsed(self) -> float:
        end = self.end_time if self.end_time else time.monotonic()
        return end - self.start_time

    @property
    def step_count(self) -> int:
        return len(self.steps)


REACT_SYSTEM_PROMPT = """You are Forge, an expert agentic coding assistant that runs 100% locally.

## How You Think (ReAct Pattern)

For every task, you follow this pattern:
1. **REASON** — Analyze what needs to happen. Think step by step.
2. **ACT** — Use a tool to make progress. Be specific and precise.
3. **OBSERVE** — Carefully examine the tool result.
4. **REFLECT** — Did it work? What's the next step? Do I need to adjust?

## Core Principles

**Be surgical.** Use `edit` for changes, not `write`. Read before editing. Know exactly what you're changing.

**Be systematic.** For complex tasks:
- First: understand the codebase (read relevant files, search for patterns)
- Second: plan your approach (think through the changes needed)
- Third: execute step by step (make changes, verify each one)
- Fourth: validate (run tests, check for errors)

**Be self-correcting.** When something fails:
1. Read the error message carefully
2. Understand WHY it failed
3. Adjust your approach
4. Retry with the fix
Don't just retry the same thing — adapt.

**Be context-aware.** Before making changes:
- Read the file you're editing
- Understand the existing patterns and conventions
- Check for related files that might need updating
- Look at imports and dependencies

**Be efficient.** Batch related operations. Don't read files you don't need. Don't make unnecessary round trips.

## Tool Usage

- `read` — Always read a file before editing it
- `edit` — For precise, surgical changes (preferred)
- `write` — Only for new files or complete rewrites
- `shell` — For running commands (tests, builds, git)
- `search` — For finding code patterns across the codebase
- `find_symbol` — For finding functions/classes by name (AST-aware)
- `semantic_search` — For finding code by meaning
- `analyze_errors` — For parsing and understanding error output
- `git_workflow` — For git operations
- `test` — For running tests
- `think` — For complex reasoning (record your thought process)

## Error Recovery

When a tool call fails:
1. Read the error carefully — it usually tells you exactly what's wrong
2. If it's a file edit failure: re-read the file, the content may have changed
3. If it's a test failure: analyze the test output, understand the assertion
4. If it's a build error: parse the error, fix the source
5. After fixing: re-run the failed operation to verify

## Response Quality

- Write clean, well-structured code
- Follow existing conventions in the project
- Add type hints where appropriate
- Handle errors gracefully
- Write tests for new functionality
- Update documentation when changing behavior

## What NOT to Do

- Don't guess at file contents — read them first
- Don't retry the same failing approach — adapt
- Don't make changes without understanding the context
- Don't ignore error messages — they contain the solution
- Don't write overly complex solutions — simplicity wins
- Don't skip verification — always check your work"""


class ReActAgent:
    """
    ReAct (Reasoning + Acting) agent with self-correction.

    This is the core intelligence of Forge. It:
    1. Reasons about what to do (chain of thought)
    2. Acts by calling tools
    3. Observes results
    4. Reflects on progress
    5. Self-corrects when things go wrong
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
        self.conv_context = ConversationContext(max_tokens=config.max_context_tokens)
        self.run: Optional[AgentRun] = None

        # Callbacks
        self._on_thought: Optional[Callable] = None
        self._on_action: Optional[Callable] = None
        self._on_observation: Optional[Callable] = None
        self._on_token: Optional[Callable] = None
        self._on_phase: Optional[Callable] = None

    def on_thought(self, cb: Callable) -> None:
        self._on_thought = cb

    def on_action(self, cb: Callable) -> None:
        self._on_action = cb

    def on_observation(self, cb: Callable) -> None:
        self._on_observation = cb

    def on_token(self, cb: Callable) -> None:
        self._on_token = cb

    def on_phase(self, cb: Callable) -> None:
        self._on_phase = cb

    def _set_phase(self, phase: AgentPhase) -> None:
        if self._on_phase:
            self._on_phase(phase)

    async def run_task(self, task: str, stream: bool = True) -> str:
        """
        Execute a task end-to-end using the ReAct pattern.

        Returns the final response text.
        """
        self.run = AgentRun(task=task)

        # Build system context
        system = self._build_system_prompt()

        # Initialize conversation
        self.conv_context.set_system(system)
        self.conv_context.add_user_message(task)

        # Execute ReAct loop
        max_iterations = self.config.max_iterations
        iteration = 0
        consecutive_errors = 0

        while iteration < max_iterations:
            iteration += 1

            self._set_phase(AgentPhase.REASONING)

            # Get LLM response (with tools)
            try:
                response = await self._get_response(stream)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                self.run.total_errors += 1
                error_msg = f"LLM error ({consecutive_errors}/{3}): {type(e).__name__}: {str(e)}"

                if consecutive_errors >= 3:
                    self.run.final_response = f"I encountered repeated LLM errors. Last error: {str(e)}"
                    break

                self.conv_context.add_user_message(
                    f"[System] {error_msg}. Please adjust your approach and try again."
                )
                continue

            # Process the response
            if response.has_tool_calls:
                # Add assistant message with tool calls
                self.conv_context.add_assistant_message(response.content or "")

                # Execute tools
                self._set_phase(AgentPhase.EXECUTING)
                should_continue = await self._execute_tool_calls(
                    response.tool_calls, response.content
                )

                if not should_continue:
                    break

                # Check if we should verify
                if self.run and self.run.step_count > 0:
                    last_step = self.run.steps[-1]
                    if last_step.tool_result and not last_step.tool_result.success:
                        self._set_phase(AgentPhase.RECOVERING)
                        # Auto-analyze the error
                        if last_step.tool_result.error:
                            analysis = self.error_engine.analyze(
                                last_step.tool_result.error
                            )
                            if analysis.fix_strategy:
                                self.conv_context.add_user_message(
                                    f"[Error Analysis] {analysis.summary()}\n\n"
                                    f"Fix strategy:\n{analysis.fix_strategy}\n\n"
                                    f"Please fix the issue and continue."
                                )

            else:
                # No tool calls — the LLM is done
                self.run.final_response = response.content
                self.run.success = True
                self._set_phase(AgentPhase.DONE)
                break

        # If we hit max iterations
        if iteration >= max_iterations and not self.run.final_response:
            self._set_phase(AgentPhase.SUMMARIZING)
            summary = await self._generate_summary()
            self.run.final_response = summary

        self.run.end_time = time.monotonic()
        return self.run.final_response

    def _build_system_prompt(self) -> str:
        """Build the system prompt with project context."""
        system = REACT_SYSTEM_PROMPT

        # Add project context
        summary = self.context.summary()
        if summary:
            system += f"\n\n## Current Project\n{summary}"

        # Add memory context
        try:
            from .memory import SessionMemory
            from ..config import FORGE_HOME
            memory = SessionMemory(FORGE_HOME / "memory")
            prefs = memory.get_preferences()
            if prefs:
                system += "\n\n## User Preferences\n"
                for k, v in prefs.items():
                    system += f"- {k}: {v}\n"
        except Exception:
            pass

        # Add available tools summary
        system += "\n\n## Available Tools\n"
        for tool in self.tools.definitions:
            func = tool.to_dict()["function"]
            system += f"- {func['name']}: {func['description'][:100]}\n"

        return system

    async def _get_response(self, stream: bool):
        """Get LLM response, optionally with streaming."""
        messages = self.conv_context.to_messages()

        if stream:
            return await self._stream_response(messages)
        else:
            return await self.provider.chat(
                messages=[LLMMessage(role=m["role"], content=m["content"]) for m in messages],
                tools=self.tools.definitions,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )

    async def _stream_response(self, messages: list[dict]):
        """Stream LLM response with token callbacks."""
        from ..llm.base import LLMResponse

        full_content = ""
        tool_calls = None
        finish_reason = None

        llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]

        async for chunk in self.provider.stream_chat(
            messages=llm_messages,
            tools=self.tools.definitions,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        ):
            if chunk.delta:
                full_content += chunk.delta
                if self._on_token:
                    self._on_token(chunk.delta)

            if chunk.tool_calls:
                if tool_calls is None:
                    tool_calls = []
                for tc in chunk.tool_calls:
                    idx = tc.get("index", len(tool_calls))
                    while len(tool_calls) <= idx:
                        tool_calls.append({
                            "id": "", "type": "function",
                            "function": {"name": "", "arguments": ""}
                        })
                    if "id" in tc and tc["id"]:
                        tool_calls[idx]["id"] = tc["id"]
                    func = tc.get("function", {})
                    if "name" in func and func["name"]:
                        tool_calls[idx]["function"]["name"] = func["name"]
                    if "arguments" in func:
                        tool_calls[idx]["function"]["arguments"] += func["arguments"]

            if chunk.finish_reason:
                finish_reason = chunk.finish_reason

            if chunk.done:
                break

        return LLMResponse(
            content=full_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=self.config.model,
        )

    async def _execute_tool_calls(
        self, tool_calls: list[dict], assistant_content: str
    ) -> bool:
        """Execute tool calls and add results to context. Returns False if should stop."""
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_id = tc.get("id", "")

            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            step = AgentStep(
                phase=AgentPhase.EXECUTING,
                tool_name=tool_name,
                tool_args=args,
                thought=assistant_content,
            )

            # Notify
            if self._on_action:
                self._on_action(tool_name, args)

            # Check approval
            tool_obj = self.tools.get(tool_name)
            if tool_obj and tool_obj.dangerous and self.config.confirm_destructive:
                if not self.config.auto_approve and self.display:
                    approved = await self.display.request_approval(tool_name, args)
                    if not approved:
                        result = ToolResult(
                            success=False, output=None,
                            error="User declined this action."
                        )
                        step.tool_result = result
                        self.run.steps.append(step)
                        self._add_tool_result(tool_name, result)
                        continue

            # Execute
            start = time.monotonic()
            result = await self.tools.execute(tool_name, args)
            step.duration_ms = (time.monotonic() - start) * 1000
            step.tool_result = result

            self.run.total_tool_calls += 1
            if result.artifacts:
                self.run.files_modified.extend(result.artifacts)
            if not result.success:
                self.run.total_errors += 1

            # Notify
            if self._on_observation:
                self._on_observation(tool_name, result)

            # Add to context
            self._add_tool_result(tool_name, result)
            self.run.steps.append(step)

            # Check if this was a "done" signal
            if tool_name == "task_complete":
                return False

        return True

    def _add_tool_result(self, tool_name: str, result: ToolResult) -> None:
        """Add tool result to conversation context."""
        output = result.to_string()
        # Truncate very long outputs
        if len(output) > 8000:
            output = output[:4000] + f"\n\n... ({len(output) - 8000} chars truncated) ...\n\n" + output[-4000:]

        self.conv_context.add_tool_result(tool_name, output)

    async def _generate_summary(self) -> str:
        """Generate a summary when hitting max iterations."""
        self.conv_context.add_user_message(
            "[System] You've reached the maximum iterations. "
            "Provide a clear summary of what was accomplished, "
            "what remains to be done, and any issues encountered."
        )

        messages = self.conv_context.to_messages()
        llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]

        response = await self.provider.chat(
            messages=llm_messages,
            temperature=0.3,
            max_tokens=2048,
        )
        return response.content

    async def chat(self, message: str, stream: bool = True) -> str:
        """Continue the conversation (multi-turn)."""
        self.conv_context.add_user_message(message)

        try:
            if stream:
                response = await self._stream_response(self.conv_context.to_messages())
            else:
                messages = self.conv_context.to_messages()
                llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
                response = await self.provider.chat(
                    messages=llm_messages,
                    tools=self.tools.definitions,
                    temperature=self.config.temperature,
                )
        except Exception as e:
            return f"Error: {type(e).__name__}: {str(e)}"

        self.conv_context.add_assistant_message(response.content or "")

        if response.has_tool_calls:
            await self._execute_tool_calls(response.tool_calls, response.content)

        return response.content or ""

    @property
    def stats(self) -> dict:
        """Get execution statistics."""
        stats = {
            "iterations": self.run.step_count if self.run else 0,
            "tool_calls": self.run.total_tool_calls if self.run else 0,
            "errors": self.run.total_errors if self.run else 0,
            "files_modified": len(set(self.run.files_modified)) if self.run else 0,
            "elapsed_s": round(self.run.elapsed, 2) if self.run else 0,
            "provider": self.provider.stats,
        }
        if self.run and self.run.plan:
            stats["plan_progress"] = f"{self.run.plan.progress:.0%}"
        return stats
