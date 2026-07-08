"""
Planner — breaks complex tasks into executable plans.
Supports iterative refinement and adaptive re-planning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..llm.base import LLMMessage, LLMProvider


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in a plan."""
    id: int
    description: str
    tool: Optional[str] = None
    args: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3

    @property
    def is_done(self) -> bool:
        return self.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)

    @property
    def is_failed(self) -> bool:
        return self.status == StepStatus.FAILED and self.retries >= self.max_retries


@dataclass
class Plan:
    """An execution plan with ordered steps."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    context: str = ""

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.is_done)
        return done / len(self.steps)

    @property
    def is_complete(self) -> bool:
        return all(s.is_done for s in self.steps)

    @property
    def has_failures(self) -> bool:
        return any(s.is_failed for s in self.steps)

    @property
    def current(self) -> Optional[PlanStep]:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance(self) -> Optional[PlanStep]:
        """Move to the next pending step."""
        for i, step in enumerate(self.steps):
            if step.status == StepStatus.PENDING:
                self.current_step = i
                step.status = StepStatus.IN_PROGRESS
                return step
        return None

    def mark_complete(self, step_id: int, result: str) -> None:
        for step in self.steps:
            if step.id == step_id:
                step.status = StepStatus.COMPLETED
                step.result = result
                break

    def mark_failed(self, step_id: int, error: str) -> None:
        for step in self.steps:
            if step.id == step_id:
                step.retries += 1
                if step.retries >= step.max_retries:
                    step.status = StepStatus.FAILED
                step.error = error
                break

    def format(self) -> str:
        """Format the plan for display."""
        lines = [f"📋 Plan: {self.goal}", f"Progress: {self.progress:.0%}", ""]
        for step in self.steps:
            status_icons = {
                StepStatus.PENDING: "⬜",
                StepStatus.IN_PROGRESS: "🔄",
                StepStatus.COMPLETED: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️",
            }
            icon = status_icons.get(step.status, "⬜")
            lines.append(f"  {icon} Step {step.id}: {step.description}")
            if step.error:
                lines.append(f"     ⚠️ Error: {step.error[:100]}")
        return "\n".join(lines)


PLANNER_SYSTEM_PROMPT = """You are a planning engine for an agentic coding tool called Forge.

Given a user's task, break it into a clear, ordered sequence of steps. Each step should be:
1. Specific and actionable
2. Use one of the available tools when applicable
3. Ordered logically (dependencies first)
4. Small enough to verify independently

Available tools will be provided. For each step, specify:
- description: What this step does
- tool: Which tool to use (or "reasoning" for analysis steps)
- args: Arguments for the tool (empty dict if reasoning)

Output a JSON array of steps. Example:
```json
[
  {"description": "Read the current auth module", "tool": "read", "args": {"path": "src/auth.py"}},
  {"description": "Add JWT token validation function", "tool": "edit", "args": {"path": "src/auth.py", "old_text": "...", "new_text": "..."}},
  {"description": "Run tests to verify changes", "tool": "shell", "args": {"command": "pytest tests/test_auth.py"}}
]
```

Be concrete. Use actual file paths, function names, and specific changes. Vague plans are useless.
Keep plans under 15 steps. For complex tasks, focus on the critical path."""


class Planner:
    """Generates and refines execution plans using LLM reasoning."""

    def __init__(self, provider: LLMProvider, config):
        self.provider = provider
        self.config = config

    async def create_plan(
        self,
        task: str,
        context: str = "",
        tools: Optional[list[dict]] = None,
    ) -> Plan:
        """Create an execution plan for a task."""
        tools_desc = ""
        if tools:
            tools_desc = "\n\nAvailable tools:\n"
            for t in tools:
                name = t.get("function", {}).get("name", t.get("name", "?"))
                desc = t.get("function", {}).get("description", t.get("description", ""))
                tools_desc += f"- {name}: {desc}\n"

        user_msg = f"""Task: {task}

{f'Project context:{chr(10)}{context}' if context else ''}
{tools_desc}

Create a step-by-step plan to accomplish this task. Output ONLY a JSON array of steps."""

        messages = [
            LLMMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_msg),
        ]

        response = await self.provider.chat(
            messages=messages,
            temperature=0.2,
            max_tokens=2048,
        )

        # Parse the plan
        steps = self._parse_steps(response.content)

        plan = Plan(
            goal=task,
            steps=[
                PlanStep(id=i + 1, description=s["description"], tool=s.get("tool"), args=s.get("args", {}))
                for i, s in enumerate(steps)
            ],
            context=context,
        )

        return plan

    async def replan(
        self,
        plan: Plan,
        error: str,
        context: str = "",
    ) -> Plan:
        """Re-plan after a failure, adjusting for the error."""
        completed = [
            f"✅ Step {s.id}: {s.description}" for s in plan.steps
            if s.status == StepStatus.COMPLETED
        ]
        failed = [
            f"❌ Step {s.id}: {s.description} — Error: {s.error}"
            for s in plan.steps if s.status == StepStatus.FAILED
        ]
        remaining = [
            f"⬜ Step {s.id}: {s.description}" for s in plan.steps
            if s.status == StepStatus.PENDING
        ]

        user_msg = f"""Original goal: {plan.goal}

Completed steps:
{chr(10).join(completed) if completed else 'None'}

Failed steps:
{chr(10).join(failed) if failed else 'None'}

Remaining steps:
{chr(10).join(remaining) if remaining else 'None'}

Error encountered: {error}

{f'Context:{chr(10)}{context}' if context else ''}

The previous plan had failures. Create a revised plan that:
1. Accounts for what was already done
2. Fixes or works around the failures
3. Completes the remaining work

Output ONLY a JSON array of NEW steps (not already completed ones)."""

        messages = [
            LLMMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_msg),
        ]

        response = await self.provider.chat(
            messages=messages,
            temperature=0.2,
            max_tokens=2048,
        )

        new_steps_data = self._parse_steps(response.content)

        # Keep completed steps, add new ones
        new_steps = []
        next_id = max(s.id for s in plan.steps) + 1 if plan.steps else 1
        for s in plan.steps:
            if s.status == StepStatus.COMPLETED:
                new_steps.append(s)
        for s in new_steps_data:
            new_steps.append(PlanStep(
                id=next_id,
                description=s["description"],
                tool=s.get("tool"),
                args=s.get("args", {}),
            ))
            next_id += 1

        return Plan(goal=plan.goal, steps=new_steps, context=plan.context)

    def _parse_steps(self, content: str) -> list[dict]:
        """Parse plan steps from LLM response."""
        # Try to extract JSON from the response
        content = content.strip()

        # Try direct JSON parse
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # Try to find JSON array in markdown code block
        import re
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Try to find any JSON array
        bracket_match = re.search(r'\[.*\]', content, re.DOTALL)
        if bracket_match:
            try:
                parsed = json.loads(bracket_match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Fallback: treat entire response as a single step
        return [{"description": content[:500], "tool": "reasoning", "args": {}}]
