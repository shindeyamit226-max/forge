"""
Knowledge Graph Tools — expose the brain to the agent.
These tools let the agent query relationships, analyze impact,
and navigate the codebase intelligently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .registry import ToolResult, registry


def _get_graph():
    """Get or build the knowledge graph."""
    from ..core.knowledge_graph import KnowledgeGraph
    graph = KnowledgeGraph()
    graph.build_from_directory(".")
    return graph


@registry.register(
    name="graph_who_calls",
    description="Find all functions/methods that call a given function. Use before modifying a function to understand its consumers. Returns caller names, files, and line numbers.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Function or method name to find callers of"},
        },
        "required": ["name"],
    },
    category="graph",
)
async def graph_who_calls(name: str) -> ToolResult:
    """Find who calls a function."""
    graph = _get_graph()
    callers = graph.who_calls(name)

    if not callers:
        return ToolResult(success=True, output=f"Nobody calls '{name}' (or not found in graph)")

    lines = [f"Who calls '{name}' ({len(callers)} callers):\n"]
    for c in callers:
        lines.append(f"  → {c['caller']} ({c['file']}:{c['line']})")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_what_calls",
    description="Find all functions that a given function calls. Use to understand a function's dependencies. Returns the full call tree.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Function or method name"},
        },
        "required": ["name"],
    },
    category="graph",
)
async def graph_what_calls(name: str) -> ToolResult:
    """Find what a function calls."""
    graph = _get_graph()
    callees = graph.what_does_call(name)

    if not callees:
        return ToolResult(success=True, output=f"'{name}' doesn't call anything (or not found)")

    lines = [f"What '{name}' calls ({len(callees)} callees):\n"]
    for c in callees:
        lines.append(f"  → {c['callee']} ({c['file']}:{c['line']})")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_impact",
    description="Analyze the impact of changing a function, class, or file. Shows what would break, what tests to run, and risk level. ALWAYS use this before modifying code that others depend on.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Symbol name to analyze impact of changing"},
        },
        "required": ["name"],
    },
    category="graph",
)
async def graph_impact(name: str) -> ToolResult:
    """Analyze impact of changing a symbol."""
    graph = _get_graph()
    analysis = graph.analyze_impact(name)
    return ToolResult(success=True, output=analysis.summary())


@registry.register(
    name="graph_related",
    description="Find ALL code related to a symbol — callers, callees, tests, imports, same-file code, same-class methods. Use this to understand the full context before making changes.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Symbol name to find related code for"},
        },
        "required": ["name"],
    },
    category="graph",
)
async def graph_related(name: str) -> ToolResult:
    """Find all related code."""
    graph = _get_graph()
    related = graph.find_related(name)

    lines = [f"Related to '{name}':\n"]

    for rel_type, items in related.items():
        if items:
            lines.append(f"  [{rel_type}]")
            for item in items[:5]:
                lines.append(f"    → {item}")
            if len(items) > 5:
                lines.append(f"    ... and {len(items) - 5} more")

    if not any(related.values()):
        lines.append("  No related code found")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_path",
    description="Find the shortest path between two symbols in the codebase. Useful for understanding how two pieces of code are connected.",
    parameters={
        "type": "object",
        "properties": {
            "from_name": {"type": "string", "description": "Starting symbol"},
            "to_name": {"type": "string", "description": "Target symbol"},
        },
        "required": ["from_name", "to_name"],
    },
    category="graph",
)
async def graph_path(from_name: str, to_name: str) -> ToolResult:
    """Find path between two symbols."""
    graph = _get_graph()
    path = graph.find_path(from_name, to_name)

    if not path:
        return ToolResult(success=True, output=f"No path found between '{from_name}' and '{to_name}'")

    return ToolResult(success=True, output=f"Path: {' → '.join(path)}")


@registry.register(
    name="graph_patterns",
    description="Detect architectural patterns and anti-patterns in the codebase. Finds: god objects, circular dependencies, dead code, long functions, high fan-in. Use for code review and refactoring guidance.",
    parameters={
        "type": "object",
        "properties": {},
    },
    category="graph",
)
async def graph_patterns() -> ToolResult:
    """Detect codebase patterns."""
    graph = _get_graph()
    patterns = graph.detect_patterns()

    if not patterns:
        return ToolResult(success=True, output="No significant patterns detected. Codebase looks healthy!")

    lines = [f"Detected {len(patterns)} patterns:\n"]

    severity_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}

    for p in patterns[:15]:
        icon = severity_icon.get(p.severity, "⚪")
        lines.append(f"  {icon} [{p.kind}] {p.name}")
        lines.append(f"     {p.description}")
        if p.suggestion:
            lines.append(f"     💡 {p.suggestion}")
        lines.append("")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_deps",
    description="Show the dependency tree of a file. What it imports, and what imports it. Use to understand module relationships.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "File path to analyze"},
        },
        "required": ["file"],
    },
    category="graph",
)
async def graph_deps(file: str) -> ToolResult:
    """Show file dependencies."""
    graph = _get_graph()

    imports = graph.what_does_depend(file)
    imported_by = graph.what_depends_on(file)

    lines = [f"Dependencies for {file}:\n"]

    if imports:
        lines.append(f"  Imports ({len(imports)}):")
        for imp in imports:
            lines.append(f"    → {imp}")
    else:
        lines.append("  Imports: none")

    if imported_by:
        lines.append(f"\n  Imported by ({len(imported_by)}):")
        for imp in imported_by:
            lines.append(f"    ← {imp}")
    else:
        lines.append("\n  Imported by: none")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_call_chain",
    description="Trace the full call chain starting from a function. Shows the execution flow through multiple levels of function calls. Essential for understanding complex workflows.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Starting function name"},
            "depth": {"type": "integer", "description": "How deep to trace (default 3)", "default": 3},
        },
        "required": ["name"],
    },
    category="graph",
)
async def graph_call_chain(name: str, depth: int = 3) -> ToolResult:
    """Trace call chains."""
    graph = _get_graph()
    chains = graph.get_call_chain(name, depth)

    if not chains:
        return ToolResult(success=True, output=f"No call chains found starting from '{name}'")

    lines = [f"Call chains from '{name}' ({len(chains)} chains):\n"]
    for i, chain in enumerate(chains[:5], 1):
        # Convert node IDs to names
        names = []
        for node_id in chain:
            node = graph.nodes.get(node_id)
            if node:
                names.append(node.qualified_name)
        lines.append(f"  Chain {i}: {' → '.join(names)}")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_stats",
    description="Show knowledge graph statistics — total nodes, edges, types, and health metrics.",
    parameters={
        "type": "object",
        "properties": {},
    },
    category="graph",
)
async def graph_stats() -> ToolResult:
    """Show graph statistics."""
    graph = _get_graph()
    stats = graph.stats

    lines = ["Knowledge Graph Statistics:\n"]
    lines.append(f"  Nodes: {stats['total_nodes']}")
    lines.append(f"  Edges: {stats['total_edges']}")
    lines.append(f"  Files: {stats['files']}")
    lines.append(f"  Unique names: {stats['unique_names']}")

    if stats['node_types']:
        lines.append("\n  Node types:")
        for kind, count in sorted(stats['node_types'].items(), key=lambda x: -x[1]):
            lines.append(f"    {kind}: {count}")

    if stats['edge_types']:
        lines.append("\n  Edge types:")
        for kind, count in sorted(stats['edge_types'].items(), key=lambda x: -x[1]):
            lines.append(f"    {kind}: {count}")

    return ToolResult(success=True, output="\n".join(lines))
