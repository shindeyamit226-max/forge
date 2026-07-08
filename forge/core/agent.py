"""
Agent Engine — the brain of Forge.
Orchestrates planning, tool execution, and self-correction loops.
This is where the magic happens.
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from ..llm.base import LLMMessage, LLMProvider, StreamChunk, ToolDefinition
from ..tools.registry import ToolRegistry, ToolResult
from .context import ProjectContext
from .planner import Plan, Planner, StepStatus


SYSTEM_PROMPT = """You are Forge, an expert agentic coding assistant. You run 100% locally on the user's machine.

## Core Principles
1. **Think before acting** — analyze the codebase, understand the task, then plan your approach
2. **Be precise** — use exact file paths, exact text for edits, exact commands
3. **Verify your work** — run tests, check for errors, validate changes
4. **Self-correct** — if something fails, analyze why and try a different approach
5. **Be efficient** — batch related operations, minimize unnecessary file reads
6. **Explain clearly** — tell the user what you're doing and why

## How You Work
- You have access to tools that let you read, write, edit files, run commands, search code, and more
- For complex tasks, think step by step and use multiple tools in sequence
- When editing code, prefer `edit` over `write` for surgical changes
- When you encounter errors, analyze them and retry with fixes
- Always verify critical changes (run tests, check syntax)

## Code Quality
- Write clean, well-structured code with proper error handling
- Follow existing code style and conventions in the project
- Add comments for complex logic, not for obvious code
- Use type hints where the language supports them
- Consider edge cases and potential failure modes

## Safety
- Never execute destructive commands without explicit user approval
- Prefer `trash` over `rm` when possible
- Be careful with git operations (especially force push, reset --hard)
- Don't modify files outside the project directory unless asked
- If unsure about an action, ask the user first

## Response Format
- Be conversational but concise
- Use markdown for formatting (code blocks, lists, headers)
- When showing code changes, show the diff or relevant snippet
- After completing a task, summarize what was done and any remaining issues"""


@dataclass
class AgentState:
    """Tracks the agent's current state."""
    messages: list[LLMMessage] = field(default_factory=list)
    plan: Optional[Plan] = None
    iteration: int = 0
    total_tokens: int = 0
    start_time: float = 0.0
    tool_calls_made: int = 0
    errors_encountered: int = 0
    files_modified: list[str] = field(default_factory=list)
    is_complete: bool = False
    final_response: str = ""

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time if self.start_time else 0.0


class Agent:
    """
    The Forge agent — orchestrates LLM, tools, and planning to accomplish tasks.

    Features:
    - Multi-step task planning and execution
    - Self-correcting error loops
    - Streaming responses
    - Context-aware code understanding
    - Project-wide analysis
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
        self.state = AgentState()
        self._on_tool_start: Optional[Callable] = None
        self._on_tool_end: Optional[Callable] = None
        self._on_token: Optional[Callable] = None

    def on_tool_start(self, callback: Callable) -> None:
        self._on_tool_start = callback

    def on_tool_end(self, callback: Callable) -> None:
        self._on_tool_end = callback

    def on_token(self, callback: Callable) -> None:
        self._on_token = callback

    async def run(self, task: str, stream: bool = True) -> str:
        """
        Execute a task end-to-end.

        1. Build context from the project
        2. Create a plan (if complex)
        3. Execute steps using LLM + tools
        4. Self-correct on errors
        5. Return final response
        """
        self.state = AgentState(start_time=time.monotonic())

        # Build context
        project_summary = self.context.summary()
        relevant_files = self.context.get_relevant_files(task)

        # Read relevant files for context
        file_contexts = []
        for fpath in relevant_files[:10]:
            try:
                from pathlib import Path
                content = Path(fpath).read_text(errors="replace")
                if len(content) > 3000:
                    content = content[:3000] + "\n... (truncated)"
                file_contexts.append(f"--- {fpath} ---\n{content}")
            except Exception:
                pass

        # Build system message
        system_msg = SYSTEM_PROMPT
        if project_summary:
            system_msg += f"\n\n## Current Project\n{project_summary}"
        if file_contexts:
            system_msg += f"\n\n## Relevant Files\n" + "\n\n".join(file_contexts)

        # Initialize conversation
        self.state.messages = [
            LLMMessage(role="system", content=system_msg),
            LLMMessage(role="user", content=task),
        ]

        # Agent loop
        response_text = ""
        while self.state.iteration < self.config.max_iterations:
            self.state.iteration += 1

            try:
                if stream:
                    response = await self._stream_turn()
                else:
                    response = await self._normal_turn()
            except Exception as e:
                self.state.errors_encountered += 1
                error_msg = f"LLM error: {type(e).__name__}: {str(e)}"
                self.state.messages.append(
                    LLMMessage(role="user", content=f"[System Error] {error_msg}. Please try again or adjust your approach.")
                )
                continue

            response_text = response.content

            # Add assistant response to history
            self.state.messages.append(
                LLMMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            # If no tool calls, we're done
            if not response.has_tool_calls:
                self.state.is_complete = True
                self.state.final_response = response.content
                break

            # Execute tool calls
            await self._execute_tools(response.tool_calls)

            # Check if we should continue
            if self.state.plan and self.state.plan.is_complete:
                self.state.is_complete = True
                break

        # If we hit max iterations, generate a final summary
        if not self.state.is_complete:
            summary_prompt = (
                f"[System] You've reached the maximum iterations ({self.config.max_iterations}). "
                f"Please provide a summary of what was accomplished and any remaining work."
            )
            self.state.messages.append(LLMMessage(role="user", content=summary_prompt))

            try:
                final = await self.provider.chat(self.state.messages, temperature=0.3)
                self.state.final_response = final.content
            except Exception:
                self.state.final_response = response_text or "Task incomplete — maximum iterations reached."

        return self.state.final_response

    async def _normal_turn(self):
        """Execute a single LLM turn without streaming."""
        return await self.provider.chat(
            messages=self.state.messages,
            tools=self.tools.definitions,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    async def _stream_turn(self):
        """Execute a single LLM turn with streaming."""
        full_content = ""
        tool_calls = None
        finish_reason = None

        async for chunk in self.provider.stream_chat(
            messages=self.state.messages,
            tools=self.tools.definitions,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        ):
            if chunk.delta:
                full_content += chunk.delta
                if self._on_token:
                    self._on_token(chunk.delta)

            if chunk.tool_calls:
                # Accumulate tool call deltas
                if tool_calls is None:
                    tool_calls = []
                # Handle streaming tool call accumulation
                for tc in chunk.tool_calls:
                    if len(tool_calls) <= tc.get("index", 0):
                        tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    idx = tc.get("index", 0)
                    if idx < len(tool_calls):
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

        from ..llm.base import LLMResponse
        return LLMResponse(
            content=full_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=self.config.model,
        )

    async def _execute_tools(self, tool_calls: list[dict]) -> None:
        """Execute tool calls and add results to conversation."""
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_id = tc.get("id", "")

            # Parse arguments
            try:
                args = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            # Notify UI
            if self._on_tool_start:
                self._on_tool_start(tool_name, args)

            self.state.tool_calls_made += 1

            # Check if tool needs approval
            tool_obj = self.tools.get(tool_name)
            if tool_obj and (tool_obj.dangerous or tool_obj.requires_approval):
                if self.config.confirm_destructive and not self.config.auto_approve:
                    if self.display:
                        approved = await self.display.request_approval(tool_name, args)
                        if not approved:
                            result = ToolResult(
                                success=False,
                                output=None,
                                error="User declined to execute this tool.",
                            )
                            self._add_tool_result(tool_id, tool_name, result)
                            continue

            # Execute the tool
            result = await self.tools.execute(tool_name, args)

            # Track modifications
            if result.artifacts:
                self.state.files_modified.extend(result.artifacts)

            # Notify UI
            if self._on_tool_end:
                self._on_tool_end(tool_name, result)

            # Add result to conversation
            self._add_tool_result(tool_id, tool_name, result)

            # If a step failed, consider re-planning
            if not result.success and self.state.plan:
                current = self.state.plan.current
                if current:
                    self.state.plan.mark_failed(current.id, result.error or "Unknown error")
                    if current.is_failed:
                        # Step has exhausted retries, try to replan
                        try:
                            self.state.plan = await self.planner.replan(
                                self.state.plan,
                                result.error or "Unknown error",
                                self.context.summary(),
                            )
                            if self.display:
                                self.display.show_plan(self.state.plan)
                        except Exception:
                            pass

    def _add_tool_result(self, tool_id: str, tool_name: str, result: ToolResult) -> None:
        """Add a tool result to the conversation."""
        content = result.to_string()
        if len(content) > 8000:
            content = content[:4000] + f"\n\n... ({len(content) - 8000} chars truncated) ...\n\n" + content[-4000:]

        self.state.messages.append(
            LLMMessage(
                role="tool",
                content=content,
                tool_call_id=tool_id,
                name=tool_name,
            )
        )

    async def chat(self, message: str, stream: bool = True) -> str:
        """
        Continue the conversation (multi-turn).
        Maintains context from previous interactions.
        """
        self.state.messages.append(LLMMessage(role="user", content=message))

        try:
            if stream:
                response = await self._stream_turn()
            else:
                response = await self._normal_turn()
        except Exception as e:
            return f"Error: {type(e).__name__}: {str(e)}"

        self.state.messages.append(
            LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            )
        )

        if response.has_tool_calls:
            await self._execute_tools(response.tool_calls)

            # Get final response after tool execution
            final = await self.provider.chat(
                self.state.messages,
                tools=self.tools.definitions,
                temperature=self.config.temperature,
            )
            self.state.messages.append(
                LLMMessage(role="assistant", content=final.content, tool_calls=final.tool_calls)
            )
            return final.content

        return response.content

    @property
    def stats(self) -> dict:
        """Get agent execution statistics."""
        return {
            "iterations": self.state.iteration,
            "tool_calls": self.state.tool_calls_made,
            "errors": self.state.errors_encountered,
            "files_modified": len(set(self.state.files_modified)),
            "elapsed_s": round(self.state.elapsed, 2),
            "provider_stats": self.provider.stats,
        }
