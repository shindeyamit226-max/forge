"""
Backlinks Panel — like Obsidian's backlinks, but for code.
Shows everything that references a symbol: callers, tests, docs, imports.
The killer feature that no other coding tool has.
"""

from __future__ import annotations

from .registry import ToolResult, registry


def _get_graph():
    from ..core.knowledge_graph import KnowledgeGraph
    graph = KnowledgeGraph()
    graph.build_from_directory(".")
    return graph


@registry.register(
    name="backlinks",
    description="Show ALL references to a symbol — like Obsidian's backlinks panel. Shows callers, importers, tests, related code, and git history. The complete picture of how a symbol is used.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Symbol name (function, class, method, or file)"},
        },
        "required": ["name"],
    },
    category="navigation",
)
async def backlinks(name: str) -> ToolResult:
    """Show all references to a symbol — the Obsidian experience for code."""
    graph = _get_graph()
    related = graph.find_related(name)

    lines = [f"📎 Backlinks for '{name}':\n"]

    # Callers (who uses this)
    if related["callers"]:
        lines.append(f"  🔗 Called by ({len(related['callers'])}):")
        for c in related["callers"][:10]:
            lines.append(f"    ← {c}")

    # Importers (who imports this file)
    if related["imported_by"]:
        lines.append(f"\n  📦 Imported by ({len(related['imported_by'])}):")
        for i in related["imported_by"][:10]:
            lines.append(f"    ← {i}")

    # Tests
    if related["tests"]:
        lines.append(f"\n  🧪 Tested by ({len(related['tests'])}):")
        for t in related["tests"][:10]:
            lines.append(f"    ✓ {t}")

    # Same file (siblings)
    if related["same_file"]:
        lines.append(f"\n  📄 Same file ({len(related['same_file'])}):")
        for s in related["same_file"][:10]:
            lines.append(f"    · {s}")

    # Same class
    if related["same_class"]:
        lines.append(f"\n  🏗️ Same class ({len(related['same_class'])}):")
        for s in related["same_class"][:10]:
            lines.append(f"    · {s}")

    # Dependencies
    if related["callees"]:
        lines.append(f"\n  ⬇️ Depends on ({len(related['callees'])}):")
        for c in related["callees"][:10]:
            lines.append(f"    → {c}")

    if not any(related.values()):
        lines.append("  No references found")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_view",
    description="Generate a visual graph of code relationships. Outputs Mermaid diagram showing how symbols connect. Use to understand architecture and find unexpected connections.",
    parameters={
        "type": "object",
        "properties": {
            "focus": {"type": "string", "description": "Center the graph on this symbol (optional)", "default": ""},
            "depth": {"type": "integer", "description": "How many levels deep to show (default 2)", "default": 2},
        },
    },
    category="navigation",
)
async def graph_view(focus: str = "", depth: int = 2) -> ToolResult:
    """Generate a visual graph of code relationships."""
    graph = _get_graph()

    if focus:
        mermaid = graph.to_mermaid(focus=focus, depth=depth)
        lines = [f"Graph centered on '{focus}':\n"]
        lines.append("```mermaid")
        lines.append(mermaid)
        lines.append("```")
    else:
        stats = graph.stats
        lines = ["Knowledge Graph Overview:\n"]
        lines.append(f"  Nodes: {stats['total_nodes']}")
        lines.append(f"  Edges: {stats['total_edges']}")
        lines.append(f"  Files: {stats['files']}")

        if stats.get("node_types"):
            lines.append("\n  Node types:")
            for kind, count in sorted(stats["node_types"].items(), key=lambda x: -x[1]):
                lines.append(f"    {kind}: {count}")

        if stats.get("edge_types"):
            lines.append("\n  Relationship types:")
            for kind, count in sorted(stats["edge_types"].items(), key=lambda x: -x[1]):
                lines.append(f"    {kind}: {count}")

        # Show top connected nodes
        lines.append("\n  Most connected symbols:")
        node_connections = []
        for node_id, node in graph.nodes.items():
            if node.kind.value in ("function", "class", "method"):
                conns = len(graph._adjacency.get(node_id, set())) + len(graph._reverse_adj.get(node_id, set()))
                if conns > 0:
                    node_connections.append((conns, node.qualified_name, node.file))
        node_connections.sort(reverse=True)
        for conns, name, file in node_connections[:10]:
            lines.append(f"    {name} ({conns} connections) — {file}")

    return ToolResult(success=True, output="\n".join(lines))


@registry.register(
    name="graph_neighbors",
    description="Show the immediate neighborhood of a symbol — what's directly connected. Use for quick context without the full backlinks panel.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Symbol name"},
        },
        "required": ["name"],
    },
    category="navigation",
)
async def graph_neighbors(name: str) -> ToolResult:
    """Show immediate neighbors of a symbol."""
    graph = _get_graph()
    neighbors = graph.get_neighbors(name)

    if not neighbors:
        return ToolResult(success=True, output=f"No neighbors found for '{name}'")

    lines = [f"Neighbors of '{name}':\n"]
    for rel_type, items in neighbors.items():
        icon = "→" if not rel_type.startswith("_") else "←"
        clean_type = rel_type.lstrip("_")
        lines.append(f"  {icon} {clean_type}:")
        for item in items[:5]:
            lines.append(f"    {item}")

    return ToolResult(success=True, output="\n".join(lines))
