"""
Knowledge Graph — the BRAIN of Forge.
Like Obsidian's graph view, but for code.
Every function, class, module, file is a node.
Every call, import, reference, dependency is an edge.

This is what makes Forge genuinely world-class:
- Change a function → instantly know what breaks
- Ask "who calls this?" → get the full call chain
- Ask "what depends on this module?" → get the dependency tree
- Pattern detection → find architectural anti-patterns
- Impact analysis → predict consequences before making changes
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Set

from .ast_editor import CodeSymbol, parse_file, get_parser, PythonASTParser


class NodeType(str, Enum):
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    MODULE = "module"
    PACKAGE = "package"
    TEST = "test"
    INTERFACE = "interface"
    CONFIG = "config"


class EdgeType(str, Enum):
    CALLS = "calls"              # function A calls function B
    IMPORTS = "imports"          # file A imports from file B
    CONTAINS = "contains"        # file contains function/class
    INHERITS = "inherits"        # class A extends class B
    IMPLEMENTS = "implements"    # class implements interface
    DEPENDS_ON = "depends_on"    # module depends on module
    TESTS = "tests"              # test file tests source file
    OVERRIDES = "overrides"      # method overrides parent method
    RETURNS = "returns"          # function returns type
    ACCEPTS = "accepts"          # function parameter type
    CREATES = "creates"          # function creates instance of
    MODIFIES = "modifies"        # function modifies variable
    REFERENCES = "references"    # generic reference
    SERVED_BY = "served_by"      # route served by handler
    MIGRATES = "migrates"        # migration modifies table


@dataclass
class Node:
    """A node in the knowledge graph."""
    id: str
    kind: NodeType
    name: str
    file: str
    line: int = 0
    end_line: int = 0
    signature: str = ""
    docstring: str = ""
    language: str = ""
    hash: str = ""          # Content hash for change detection
    metadata: dict = field(default_factory=dict)
    tags: set = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)

    @property
    def qualified_name(self) -> str:
        return self.metadata.get("qualified_name", self.name)

    def __hash__(self):
        return hash(self.id)


@dataclass
class Edge:
    """An edge in the knowledge graph."""
    source: str  # source node id
    target: str  # target node id
    kind: EdgeType
    weight: float = 1.0
    line: int = 0       # Where this relationship occurs
    context: str = ""   # Surrounding code
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}->{self.target}:{self.kind}"


@dataclass
class ImpactAnalysis:
    """Result of analyzing the impact of a change."""
    changed_node: str
    direct_impacts: list[str] = field(default_factory=list)    # Directly affected
    indirect_impacts: list[str] = field(default_factory=list)  # Transitively affected
    test_files: list[str] = field(default_factory=list)        # Tests to run
    risk_level: str = "low"                                    # low/medium/high/critical
    risk_reasons: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Impact Analysis for: {self.changed_node}"]
        lines.append(f"Risk Level: {self.risk_level.upper()}")
        lines.append("")

        if self.direct_impacts:
            lines.append(f"Direct impacts ({len(self.direct_impacts)}):")
            for imp in self.direct_impacts[:10]:
                lines.append(f"  → {imp}")

        if self.indirect_impacts:
            lines.append(f"Indirect impacts ({len(self.indirect_impacts)}):")
            for imp in self.indirect_impacts[:10]:
                lines.append(f"  →→ {imp}")

        if self.test_files:
            lines.append(f"\nTests to run ({len(self.test_files)}):")
            for t in self.test_files[:5]:
                lines.append(f"  🧪 {t}")

        if self.risk_reasons:
            lines.append(f"\nRisk factors:")
            for r in self.risk_reasons:
                lines.append(f"  ⚠️ {r}")

        if self.suggested_actions:
            lines.append(f"\nSuggested actions:")
            for a in self.suggested_actions:
                lines.append(f"  💡 {a}")

        return "\n".join(lines)


@dataclass
class Pattern:
    """A detected pattern in the codebase."""
    name: str
    kind: str  # anti_pattern, good_pattern, architecture, convention
    description: str
    files: list[str] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)
    severity: str = "info"  # info, warning, error
    suggestion: str = ""


class KnowledgeGraph:
    """
    The brain of Forge — a knowledge graph of the entire codebase.

    Capabilities:
    - Build from AST parsing (Python, JS, TS, Go, Rust)
    - Query relationships (who calls X? what does Y depend on?)
    - Impact analysis (what breaks if I change X?)
    - Pattern detection (find anti-patterns, architectural issues)
    - Change tracking (what changed since last scan?)
    - Navigation (find related code, follow call chains)
    """

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._adjacency: dict[str, set[str]] = defaultdict(set)    # node -> neighbors
        self._reverse_adj: dict[str, set[str]] = defaultdict(set)  # node <- neighbors
        self._callers: dict[str, set[str]] = defaultdict(set)      # func <- callers
        self._callees: dict[str, set[str]] = defaultdict(set)      # func -> callees
        self._imports: dict[str, set[str]] = defaultdict(set)      # file -> imported files
        self._imported_by: dict[str, set[str]] = defaultdict(set)  # file <- imported by
        self._file_nodes: dict[str, list[str]] = defaultdict(list) # file -> node ids
        self._name_index: dict[str, list[str]] = defaultdict(list) # name -> node ids
        self._change_log: list[dict] = []
        self._last_scan: float = 0
        self._file_hashes: dict[str, str] = {}

    # ============================================================
    # BUILDING THE GRAPH
    # ============================================================

    def build_from_directory(self, root: str, extensions: Optional[set[str]] = None) -> dict:
        """Build the knowledge graph from an entire directory."""
        from .context import IGNORE_DIRS, CODE_EXTENSIONS

        if extensions is None:
            extensions = CODE_EXTENSIONS

        root_path = Path(root).resolve()
        stats = {"files": 0, "nodes": 0, "edges": 0, "errors": 0}

        # Phase 1: Parse all files and create nodes
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()

                if ext not in extensions:
                    continue

                rel_path = str(fpath.relative_to(root_path))

                # Check if file changed
                try:
                    content = fpath.read_text(errors="replace")
                except Exception:
                    stats["errors"] += 1
                    continue

                content_hash = hashlib.md5(content.encode()).hexdigest()
                if self._file_hashes.get(rel_path) == content_hash:
                    continue

                self._file_hashes[rel_path] = content_hash
                stats["files"] += 1

                # Create file node
                file_node = self._add_node(Node(
                    id=f"file:{rel_path}",
                    kind=NodeType.FILE,
                    name=fname,
                    file=rel_path,
                    language=ext.lstrip("."),
                    hash=content_hash,
                ))

                # Parse and create symbol nodes
                try:
                    symbols = self._parse_and_add_symbols(content, rel_path, ext)
                    stats["nodes"] += len(symbols) + 1

                    # Create CONTAINS edges
                    for sym in symbols:
                        self._add_edge(Edge(
                            source=file_node.id,
                            target=f"{rel_path}:{sym.name}:{sym.line}",
                            kind=EdgeType.CONTAINS,
                            line=sym.line,
                        ))

                    # Detect imports and create edges
                    import_edges = self._detect_imports(content, rel_path, ext, root_path)
                    stats["edges"] += len(import_edges) + len(symbols)

                except Exception:
                    stats["errors"] += 1

        # Phase 2: Build call graph from cross-references
        call_edges = self._build_call_graph()
        stats["edges"] += call_edges

        # Phase 3: Detect test relationships
        test_edges = self._detect_test_relationships()
        stats["edges"] += test_edges

        self._last_scan = time.time()
        return stats

    def _add_node(self, node: Node) -> Node:
        """Add a node to the graph."""
        self.nodes[node.id] = node
        self._name_index[node.name.lower()].append(node.id)

        if node.file:
            self._file_nodes[node.file].append(node.id)

        return node

    def _add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)
        self._adjacency[edge.source].add(edge.target)
        self._reverse_adj[edge.target].add(edge.source)

        if edge.kind == EdgeType.CALLS:
            self._callees[edge.source].add(edge.target)
            self._callers[edge.target].add(edge.source)
        elif edge.kind == EdgeType.IMPORTS:
            self._imports[edge.source].add(edge.target)
            self._imported_by[edge.target].add(edge.source)

    def _parse_and_add_symbols(self, content: str, filepath: str, ext: str) -> list[CodeSymbol]:
        """Parse file and create nodes for all symbols."""
        parser = get_parser(filepath)
        if not parser:
            return []

        symbols = parser.parse(content, filepath)
        for sym in symbols:
            if sym.kind in ("import",):
                continue

            node_type = {
                "function": NodeType.FUNCTION,
                "class": NodeType.CLASS,
                "method": NodeType.METHOD,
                "variable": NodeType.VARIABLE,
            }.get(sym.kind, NodeType.FUNCTION)

            node_id = f"{filepath}:{sym.name}:{sym.line}"

            # Check for test functions
            if sym.name.startswith("test_") or sym.name.startswith("Test"):
                node_type = NodeType.TEST

            self._add_node(Node(
                id=node_id,
                kind=node_type,
                name=sym.name,
                file=filepath,
                line=sym.line,
                end_line=sym.end_line,
                signature=f"{sym.name}({', '.join(sym.params)})" if sym.params else sym.name,
                docstring=sym.docstring or "",
                language=ext.lstrip("."),
                metadata={
                    "qualified_name": sym.qualified_name,
                    "parent": sym.parent,
                    "decorators": sym.decorators,
                    "params": sym.params,
                    "return_type": sym.return_type,
                },
            ))

        return symbols

    def _detect_imports(self, content: str, filepath: str, ext: str, root: Path) -> int:
        """Detect imports and create IMPORTS edges."""
        edges = 0
        lines = content.splitlines()

        for line in lines:
            stripped = line.strip()

            # Python imports
            if ext in (".py", ".pyi"):
                if stripped.startswith("from ") and " import " in stripped:
                    module = stripped.split("from ")[1].split(" import ")[0].strip()
                    # Convert module path to file path
                    module_path = module.replace(".", "/") + ".py"
                    if (root / module_path).exists():
                        rel_module = str((root / module_path).relative_to(root))
                        self._add_edge(Edge(
                            source=filepath,
                            target=rel_module,
                            kind=EdgeType.IMPORTS,
                        ))
                        edges += 1

                elif stripped.startswith("import "):
                    modules = stripped[7:].split(",")
                    for mod in modules:
                        mod = mod.strip().split(" as ")[0].strip()
                        module_path = mod.replace(".", "/") + ".py"
                        if (root / module_path).exists():
                            rel_module = str((root / module_path).relative_to(root))
                            self._add_edge(Edge(
                                source=filepath,
                                target=rel_module,
                                kind=EdgeType.IMPORTS,
                            ))
                            edges += 1

            # JavaScript/TypeScript imports
            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                if "from " in stripped and ("import " in stripped or "require(" in stripped):
                    # Extract import path
                    if "'" in stripped or '"' in stripped:
                        quote = "'" if "'" in stripped else '"'
                        parts = stripped.split(quote)
                        if len(parts) >= 2:
                            import_path = parts[1]
                            if import_path.startswith("."):
                                # Resolve relative import
                                base = Path(filepath).parent
                                resolved = (base / import_path).resolve()
                                for suffix in ["", ".js", ".ts", ".jsx", ".tsx", "/index.js", "/index.ts"]:
                                    candidate = str(resolved) + suffix
                                    if Path(candidate).exists():
                                        rel = str(Path(candidate).relative_to(root))
                                        self._add_edge(Edge(
                                            source=filepath,
                                            target=rel,
                                            kind=EdgeType.IMPORTS,
                                        ))
                                        edges += 1
                                        break

        return edges

    def _build_call_graph(self) -> int:
        """Build cross-file call relationships."""
        edges = 0

        # For each function, check if it calls functions defined in other files
        for node_id, node in self.nodes.items():
            if node.kind not in (NodeType.FUNCTION, NodeType.METHOD):
                continue

            # Read the function body
            try:
                filepath = Path(node.file)
                if not filepath.exists():
                    continue
                lines = filepath.read_text(errors="replace").splitlines()
                start = max(0, node.line - 1)
                end = min(len(lines), node.end_line)
                body = "\n".join(lines[start:end])
            except Exception:
                continue

            # Find function calls in the body
            for name in self._name_index:
                if len(name) < 3:  # Skip short names
                    continue
                if name in body.lower():
                    # Check if it's a function/method call
                    import re
                    pattern = rf'\b{re.escape(name)}\s*\('
                    if re.search(pattern, body, re.IGNORECASE):
                        # Find the target node
                        for target_id in self._name_index[name]:
                            target = self.nodes.get(target_id)
                            if target and target.kind in (NodeType.FUNCTION, NodeType.METHOD):
                                if target.file != node.file:  # Cross-file only
                                    self._add_edge(Edge(
                                        source=node_id,
                                        target=target_id,
                                        kind=EdgeType.CALLS,
                                    ))
                                    edges += 1

        return edges

    def _detect_test_relationships(self) -> int:
        """Detect which test files test which source files."""
        edges = 0

        test_files = [n for n in self.nodes.values() if n.kind == NodeType.TEST]
        source_files = [n for n in self.nodes.values()
                       if n.kind == NodeType.FILE and n.language in ("py", "js", "ts")]

        for test in test_files:
            test_name = Path(test.file).stem.lower()

            for source in source_files:
                source_name = Path(source.file).stem.lower()

                # Common test naming patterns
                if (test_name == f"test_{source_name}" or
                    test_name == f"{source_name}_test" or
                    test_name == f"{source_name}.test" or
                    test_name == f"{source_name}.spec"):

                    self._add_edge(Edge(
                        source=test.file,
                        target=source.file,
                        kind=EdgeType.TESTS,
                    ))
                    edges += 1

        return edges

    # ============================================================
    # QUERYING THE GRAPH
    # ============================================================

    def who_calls(self, name: str) -> list[dict]:
        """Find all callers of a function/method."""
        results = []
        name_lower = name.lower()

        for node_id in self._name_index.get(name_lower, []):
            callers = self._callers.get(node_id, set())
            for caller_id in callers:
                caller = self.nodes.get(caller_id)
                if caller:
                    results.append({
                        "caller": caller.qualified_name,
                        "file": caller.file,
                        "line": caller.line,
                        "kind": caller.kind.value,
                    })

        return results

    def what_does_call(self, name: str) -> list[dict]:
        """Find all functions called by a function."""
        results = []
        name_lower = name.lower()

        for node_id in self._name_index.get(name_lower, []):
            callees = self._callees.get(node_id, set())
            for callee_id in callees:
                callee = self.nodes.get(callee_id)
                if callee:
                    results.append({
                        "callee": callee.qualified_name,
                        "file": callee.file,
                        "line": callee.line,
                        "kind": callee.kind.value,
                    })

        return results

    def what_depends_on(self, file: str) -> list[str]:
        """Find all files that import/depend on a file."""
        return list(self._imported_by.get(file, set()))

    def what_does_depend(self, file: str) -> list[str]:
        """Find all files that a file imports/depends on."""
        return list(self._imports.get(file, set()))

    def find_related(self, name: str) -> dict:
        """Find all code related to a name — callers, callees, tests, imports."""
        name_lower = name.lower()
        related = {
            "callers": [],
            "callees": [],
            "tests": [],
            "imported_by": [],
            "imports": [],
            "same_file": [],
            "same_class": [],
        }

        for node_id in self._name_index.get(name_lower, []):
            node = self.nodes.get(node_id)
            if not node:
                continue

            # Callers
            for cid in self._callers.get(node_id, set()):
                c = self.nodes.get(cid)
                if c:
                    related["callers"].append(c.qualified_name)

            # Callees
            for cid in self._callees.get(node_id, set()):
                c = self.nodes.get(cid)
                if c:
                    related["callees"].append(c.qualified_name)

            # Same file
            for nid in self._file_nodes.get(node.file, []):
                n = self.nodes.get(nid)
                if n and n.id != node_id:
                    related["same_file"].append(n.qualified_name)

            # Same class
            parent = node.metadata.get("parent")
            if parent:
                for nid in self._name_index.get(parent.lower(), []):
                    n = self.nodes.get(nid)
                    if n and n.kind == NodeType.CLASS:
                        related["same_class"].append(n.qualified_name)

            # Tests
            for edge in self.edges:
                if edge.kind == EdgeType.TESTS:
                    if edge.target == node.file:
                        related["tests"].append(edge.source)

        return related

    def get_call_chain(self, name: str, depth: int = 3) -> list[list[str]]:
        """Get the full call chain starting from a function."""
        chains = []
        name_lower = name.lower()

        for node_id in self._name_index.get(name_lower, []):
            self._trace_calls(node_id, [node_id], chains, depth, set())

        return chains

    def _trace_calls(
        self, node_id: str, current_chain: list[str],
        all_chains: list[list[str]], depth: int, visited: set,
    ) -> None:
        """Recursively trace call chains."""
        if depth <= 0 or node_id in visited:
            if len(current_chain) > 1:
                all_chains.append(list(current_chain))
            return

        visited.add(node_id)
        callees = self._callees.get(node_id, set())

        if not callees:
            if len(current_chain) > 1:
                all_chains.append(list(current_chain))
            return

        for callee_id in callees:
            current_chain.append(callee_id)
            self._trace_calls(callee_id, current_chain, all_chains, depth - 1, visited)
            current_chain.pop()

    # ============================================================
    # IMPACT ANALYSIS
    # ============================================================

    def analyze_impact(self, name: str) -> ImpactAnalysis:
        """Analyze the impact of changing a function/class/module."""
        name_lower = name.lower()
        analysis = ImpactAnalysis(changed_node=name)

        # Find the node
        node_ids = self._name_index.get(name_lower, [])
        if not node_ids:
            analysis.risk_level = "unknown"
            analysis.risk_reasons.append(f"Symbol '{name}' not found in graph")
            return analysis

        node_id = node_ids[0]
        node = self.nodes.get(node_id)
        if not node:
            return analysis

        # Direct impacts: who calls this?
        direct = set()
        for caller_id in self._callers.get(node_id, set()):
            caller = self.nodes.get(caller_id)
            if caller:
                direct.add(caller.qualified_name)
                analysis.direct_impacts.append(
                    f"{caller.qualified_name} ({caller.file}:{caller.line})"
                )

        # Indirect impacts: who calls the callers?
        indirect = set()
        for caller_id in self._callers.get(node_id, set()):
            for grand_caller_id in self._callers.get(caller_id, set()):
                gc = self.nodes.get(grand_caller_id)
                if gc and gc.qualified_name not in direct:
                    indirect.add(gc.qualified_name)
                    analysis.indirect_impacts.append(
                        f"{gc.qualified_name} ({gc.file}:{gc.line})"
                    )

        # Test files
        for edge in self.edges:
            if edge.kind == EdgeType.TESTS and edge.target == node.file:
                analysis.test_files.append(edge.source)

        # Also check test functions that import this
        for file_node_id in self._file_nodes.get(node.file, []):
            for edge in self.edges:
                if edge.kind == EdgeType.TESTS and edge.target == node.file:
                    if edge.source not in analysis.test_files:
                        analysis.test_files.append(edge.source)

        # Risk assessment
        total_impact = len(direct) + len(indirect)
        if total_impact > 20:
            analysis.risk_level = "critical"
            analysis.risk_reasons.append(f"High impact: {total_impact} symbols affected")
        elif total_impact > 10:
            analysis.risk_level = "high"
            analysis.risk_reasons.append(f"Significant impact: {total_impact} symbols affected")
        elif total_impact > 3:
            analysis.risk_level = "medium"
        else:
            analysis.risk_level = "low"

        # Check if it's a public API
        if node.kind in (NodeType.CLASS, NodeType.INTERFACE):
            analysis.risk_reasons.append("Changing a class/interface affects all consumers")

        # Suggested actions
        if analysis.test_files:
            analysis.suggested_actions.append(
                f"Run tests: {', '.join(Path(t).name for t in analysis.test_files[:3])}"
            )
        if direct:
            analysis.suggested_actions.append(
                f"Review {len(direct)} direct callers after changes"
            )
        if not analysis.test_files:
            analysis.suggested_actions.append("No tests found — consider adding tests first")

        return analysis

    # ============================================================
    # PATTERN DETECTION
    # ============================================================

    def detect_patterns(self) -> list[Pattern]:
        """Detect architectural patterns and anti-patterns."""
        patterns = []

        # 1. God Object — class with too many methods
        for node in self.nodes.values():
            if node.kind == NodeType.CLASS:
                methods = [
                    n for n in self.nodes.values()
                    if n.kind == NodeType.METHOD and n.metadata.get("parent") == node.name
                ]
                if len(methods) > 20:
                    patterns.append(Pattern(
                        name="God Object",
                        kind="anti_pattern",
                        description=f"Class '{node.name}' has {len(methods)} methods. Consider splitting it.",
                        files=[node.file],
                        nodes=[node.id],
                        severity="warning",
                        suggestion=f"Break {node.name} into smaller, focused classes (SRP violation)",
                    ))

        # 2. Circular Dependencies
        cycles = self._find_cycles()
        for cycle in cycles:
            patterns.append(Pattern(
                name="Circular Dependency",
                kind="anti_pattern",
                description=f"Circular import: {' → '.join(cycle)}",
                files=cycle,
                severity="error",
                suggestion="Break the cycle by introducing an interface or moving shared code",
            ))

        # 3. High Fan-in — function called by too many others
        for node_id, callers in self._callers.items():
            if len(callers) > 15:
                node = self.nodes.get(node_id)
                if node:
                    patterns.append(Pattern(
                        name="High Fan-in",
                        kind="architecture",
                        description=f"'{node.name}' is called by {len(callers)} functions",
                        files=[node.file],
                        nodes=[node_id],
                        severity="info",
                        suggestion="High fan-in is fine for utilities, but review if it's a business logic function",
                    ))

        # 4. Orphan Functions — never called
        all_called = set()
        for callers in self._callers.values():
            all_called.update(callers)

        for node_id, node in self.nodes.items():
            if node.kind in (NodeType.FUNCTION, NodeType.METHOD):
                if node_id not in all_called and not node.name.startswith("_"):
                    if not node.name.startswith("test_"):
                        patterns.append(Pattern(
                            name="Dead Code",
                            kind="anti_pattern",
                            description=f"Function '{node.name}' appears to be unused",
                            files=[node.file],
                            nodes=[node_id],
                            severity="warning",
                            suggestion="Remove dead code or add a test that exercises it",
                        ))

        # 5. Long Functions (by line count)
        for node in self.nodes.values():
            if node.kind in (NodeType.FUNCTION, NodeType.METHOD):
                lines = node.end_line - node.line
                if lines > 100:
                    patterns.append(Pattern(
                        name="Long Function",
                        kind="anti_pattern",
                        description=f"'{node.name}' is {lines} lines long",
                        files=[node.file],
                        nodes=[node.id],
                        severity="warning",
                        suggestion="Consider extracting helper functions (aim for <50 lines)",
                    ))

        return patterns

    def _find_cycles(self) -> list[list[str]]:
        """Find circular dependencies in the import graph."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: list[str]) -> None:
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._imports.get(node, set()):
                dfs(neighbor, path)

            path.pop()
            rec_stack.discard(node)

        for file_node in self.nodes:
            if self.nodes[file_node].kind == NodeType.FILE:
                dfs(file_node, [])

        return cycles[:10]  # Limit

    # ============================================================
    # NAVIGATION
    # ============================================================

    def get_neighbors(self, name: str) -> dict[str, list[str]]:
        """Get all neighbors of a node, grouped by relationship type."""
        name_lower = name.lower()
        neighbors = defaultdict(list)

        for node_id in self._name_index.get(name_lower, []):
            for edge in self.edges:
                if edge.source == node_id:
                    target = self.nodes.get(edge.target)
                    if target:
                        neighbors[edge.kind.value].append(target.qualified_name)
                elif edge.target == node_id:
                    source = self.nodes.get(edge.source)
                    if source:
                        neighbors[f"_{edge.kind.value}_by"].append(source.qualified_name)

        return dict(neighbors)

    def find_path(self, from_name: str, to_name: str) -> Optional[list[str]]:
        """Find the shortest path between two symbols in the graph."""
        from_lower = from_name.lower()
        to_lower = to_name.lower()

        from_ids = self._name_index.get(from_lower, [])
        to_ids = set(self._name_index.get(to_lower, []))

        if not from_ids or not to_ids:
            return None

        # BFS
        start = from_ids[0]
        queue = [(start, [start])]
        visited = {start}

        while queue:
            current, path = queue.pop(0)

            if current in to_ids:
                # Convert node IDs to names
                return [self.nodes[nid].qualified_name for nid in path if nid in self.nodes]

            for neighbor in self._adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

            for neighbor in self._reverse_adj.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    # ============================================================
    # CHANGE TRACKING
    # ============================================================

    def get_changes_since(self, timestamp: float) -> list[dict]:
        """Get all nodes that changed since a timestamp."""
        changes = []
        for node in self.nodes.values():
            if node.last_seen > timestamp:
                changes.append({
                    "node": node.qualified_name,
                    "kind": node.kind.value,
                    "file": node.file,
                    "line": node.line,
                })
        return changes

    # ============================================================
    # EXPORT / VISUALIZATION
    # ============================================================

    def to_d3_json(self) -> dict:
        """Export graph in D3.js compatible format for visualization."""
        nodes = []
        links = []
        node_map = {}

        for i, (nid, node) in enumerate(self.nodes.items()):
            node_map[nid] = i
            nodes.append({
                "id": i,
                "name": node.name,
                "kind": node.kind.value,
                "file": node.file,
                "line": node.line,
                "group": node.language or "unknown",
            })

        for edge in self.edges:
            source = node_map.get(edge.source)
            target = node_map.get(edge.target)
            if source is not None and target is not None:
                links.append({
                    "source": source,
                    "target": target,
                    "kind": edge.kind.value,
                    "weight": edge.weight,
                })

        return {"nodes": nodes, "links": links}

    def to_mermaid(self, focus: Optional[str] = None, depth: int = 2) -> str:
        """Export graph as Mermaid diagram."""
        lines = ["graph TD"]

        if focus:
            # Show neighborhood of a specific node
            focus_lower = focus.lower()
            shown = set()

            for node_id in self._name_index.get(focus_lower, []):
                self._mermaid_node(node_id, lines, shown, depth, 0)
        else:
            # Show all nodes (limited)
            for node_id, node in list(self.nodes.items())[:50]:
                safe_id = node_id.replace(":", "_").replace(".", "_")
                lines.append(f"    {safe_id}[\"{node.name}\"]")

        return "\n".join(lines)

    def _mermaid_node(self, node_id: str, lines: list, shown: set, max_depth: int, depth: int) -> None:
        """Recursively add nodes to mermaid diagram."""
        if node_id in shown or depth > max_depth:
            return

        shown.add(node_id)
        node = self.nodes.get(node_id)
        if not node:
            return

        safe_id = node_id.replace(":", "_").replace(".", "_")
        lines.append(f"    {safe_id}[\"{node.name}\"]")

        for neighbor in self._adjacency.get(node_id, set()):
            safe_neighbor = neighbor.replace(":", "_").replace(".", "_")
            lines.append(f"    {safe_id} --> {safe_neighbor}")
            self._mermaid_node(neighbor, lines, shown, max_depth, depth + 1)

    # ============================================================
    # STATS
    # ============================================================

    @property
    def stats(self) -> dict:
        """Graph statistics."""
        node_types = defaultdict(int)
        for n in self.nodes.values():
            node_types[n.kind.value] += 1

        edge_types = defaultdict(int)
        for e in self.edges:
            edge_types[e.kind.value] += 1

        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": dict(node_types),
            "edge_types": dict(edge_types),
            "files": len(self._file_nodes),
            "unique_names": len(self._name_index),
        }
