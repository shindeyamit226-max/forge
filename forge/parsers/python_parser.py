"""
Python Parser — full AST-based parsing using the ast module.
Extracts: functions, classes, methods, imports, exports, variables,
decorators, type hints, docstrings, async functions, comprehensions,
and call relationships.
"""

from __future__ import annotations

import ast
import re
import hashlib
from typing import Optional

from .base import BaseParser, ParseResult, Symbol, Import, Export, Relationship, Range, Position


class PythonParser(BaseParser):
    """Full Python AST parser."""

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="python")

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError as e:
            result.errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            # Try partial parsing
            return self._partial_parse(source, filepath)

        self._visit_module(tree, source, result)
        result.complexity = sum(s.complexity for s in result.symbols)
        return result

    def _visit_module(self, tree: ast.Module, source: str, result: ParseResult) -> None:
        """Visit the module and extract all symbols."""
        lines = source.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym = self._parse_function(node, result.file, lines)
                result.symbols.append(sym)
                # Parse nested symbols
                self._visit_body(node, sym.name, result, lines)

            elif isinstance(node, ast.ClassDef):
                sym = self._parse_class(node, result.file, lines)
                result.symbols.append(sym)
                # Parse methods
                self._visit_body(node, sym.name, result, lines)

            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imp = self._parse_import(node)
                result.imports.append(imp)

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result.symbols.append(Symbol(
                            name=target.id,
                            kind="variable",
                            range=self._make_range(node.lineno, node.end_lineno or node.lineno),
                            file=result.file,
                            modifiers=["module_level"],
                        ))

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                result.symbols.append(Symbol(
                    name=node.target.id,
                    kind="variable",
                    range=self._make_range(node.lineno, node.end_lineno or node.lineno),
                    file=result.file,
                    return_type=self._unparse(node.annotation),
                    modifiers=["module_level", "annotated"],
                ))

            # Detect call relationships
            for call_node in ast.walk(node):
                if isinstance(call_node, ast.Call):
                    func_name = self._get_call_name(call_node)
                    if func_name:
                        result.relationships.append(Relationship(
                            source=f"{result.file}:module:{node.lineno}",
                            target=func_name,
                            kind="calls",
                            range=self._make_range(call_node.lineno, call_node.end_lineno or call_node.lineno),
                        ))

    def _visit_body(self, node, parent_name: str, result: ParseResult, lines: list) -> None:
        """Visit the body of a function or class."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym = self._parse_function(child, result.file, lines, parent=parent_name)
                result.symbols.append(sym)
                # Recurse into nested functions
                self._visit_body(child, sym.qualified_name, result, lines)

            elif isinstance(child, ast.ClassDef):
                sym = self._parse_class(child, result.file, lines, parent=parent_name)
                result.symbols.append(sym)
                self._visit_body(child, sym.qualified_name, result, lines)

            # Detect calls within methods
            for call_node in ast.walk(child):
                if isinstance(call_node, ast.Call):
                    func_name = self._get_call_name(call_node)
                    if func_name:
                        result.relationships.append(Relationship(
                            source=f"{result.file}:{parent_name}:{call_node.lineno}",
                            target=func_name,
                            kind="calls",
                            range=self._make_range(call_node.lineno, call_node.end_lineno or call_node.lineno),
                        ))

    def _parse_function(self, node, filepath: str, lines: list, parent: str = None) -> Symbol:
        """Parse a function/method AST node."""
        is_async = isinstance(node, ast.AsyncFunctionDef)
        is_method = parent is not None

        # Parameters
        params = []
        for arg in node.args.args:
            if arg.arg in ("self", "cls"):
                continue
            param = {"name": arg.arg}
            if arg.annotation:
                param["type"] = self._unparse(arg.annotation)
            params.append(param)

        # Defaults
        defaults = node.args.defaults
        if defaults:
            for i, default in enumerate(reversed(defaults)):
                idx = len(params) - 1 - i
                if 0 <= idx < len(params):
                    params[idx]["default"] = self._unparse(default)

        # *args and **kwargs
        if node.args.vararg:
            params.append({"name": f"*{node.args.vararg.arg}", "kind": "vararg"})
        if node.args.kwarg:
            params.append({"name": f"**{node.args.kwarg.arg}", "kind": "kwarg"})

        # Return type
        return_type = self._unparse(node.returns) if node.returns else ""

        # Docstring
        docstring = ast.get_docstring(node) or ""

        # Decorators
        decorators = [self._unparse(d) for d in node.decorator_list]

        # Modifiers
        modifiers = []
        if is_async:
            modifiers.append("async")
        if is_method:
            modifiers.append("method")
        if node.name.startswith("_"):
            modifiers.append("private")
        if node.name.startswith("__") and node.name.endswith("__"):
            modifiers.append("dunder")

        # Body hash and complexity
        body_lines = lines[node.lineno - 1:(node.end_lineno or node.lineno)]
        body_text = "\n".join(body_lines)
        body_hash = self._compute_body_hash(body_text)
        complexity = self._compute_complexity(body_text)

        # Signature
        sig_parts = [p["name"] for p in params]
        sig = f"{'async ' if is_async else ''}def {node.name}({', '.join(sig_parts)})"
        if return_type:
            sig += f" -> {return_type}"

        return Symbol(
            name=node.name,
            kind="method" if is_method else "function",
            range=self._make_range(node.lineno, node.end_lineno or node.lineno),
            file=filepath,
            parent=parent,
            signature=sig,
            return_type=return_type,
            parameters=params,
            docstring=docstring,
            decorators=decorators,
            modifiers=modifiers,
            body_hash=body_hash,
            complexity=complexity,
            line_count=(node.end_lineno or node.lineno) - node.lineno + 1,
        )

    def _parse_class(self, node, filepath: str, lines: list, parent: str = None) -> Symbol:
        """Parse a class AST node."""
        # Base classes
        bases = [self._unparse(b) for b in node.bases]

        # Decorators
        decorators = [self._unparse(d) for d in node.decorator_list]

        # Docstring
        docstring = ast.get_docstring(node) or ""

        # Modifiers
        modifiers = []
        if node.name.startswith("_"):
            modifiers.append("private")

        # Keywords (metaclass, etc.)
        for kw in node.keywords:
            if kw.arg == "metaclass":
                modifiers.append(f"metaclass={self._unparse(kw.value)}")

        return Symbol(
            name=node.name,
            kind="class",
            range=self._make_range(node.lineno, node.end_lineno or node.lineno),
            file=filepath,
            parent=parent,
            signature=f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}",
            docstring=docstring,
            decorators=decorators,
            modifiers=modifiers,
            line_count=(node.end_lineno or node.lineno) - node.lineno + 1,
            metadata={"bases": bases},
        )

    def _parse_import(self, node) -> Import:
        """Parse an import statement."""
        if isinstance(node, ast.Import):
            names = []
            alias = ""
            for alias_node in node.names:
                names.append(alias_node.name)
                if alias_node.asname:
                    alias = alias_node.asname
            return Import(
                module=names[0] if names else "",
                names=names,
                alias=alias,
                range=self._make_range(node.lineno, node.end_lineno or node.lineno),
                kind="import",
            )
        else:  # ImportFrom
            module = node.module or ""
            names = [a.name for a in node.names]
            is_wildcard = any(n == "*" for n in names)
            return Import(
                module=module,
                names=names,
                is_wildcard=is_wildcard,
                is_relative=node.level > 0,
                range=self._make_range(node.lineno, node.end_lineno or node.lineno),
                kind="from_import",
                metadata={"level": node.level},
            )

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extract the name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return self._unparse(node.func)
        return None

    def _unparse(self, node) -> str:
        """Safely unparse an AST node to string."""
        if node is None:
            return ""
        try:
            return ast.unparse(node)
        except Exception:
            return "?"

    def _partial_parse(self, source: str, filepath: str) -> ParseResult:
        """Fallback: regex-based partial parsing for files with syntax errors."""
        result = ParseResult(file=filepath, language="python")

        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Functions
            m = re.match(r'^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)', stripped)
            if m:
                result.symbols.append(Symbol(
                    name=m.group(1),
                    kind="function",
                    range=self._make_range(i, i),
                    file=filepath,
                    signature=stripped.split(":")[0],
                ))

            # Classes
            m = re.match(r'^class\s+(\w+)', stripped)
            if m:
                result.symbols.append(Symbol(
                    name=m.group(1),
                    kind="class",
                    range=self._make_range(i, i),
                    file=filepath,
                ))

            # Imports
            m = re.match(r'^(?:from\s+(\S+)\s+)?import\s+(.+)', stripped)
            if m:
                result.imports.append(Import(
                    module=m.group(1) or "",
                    names=[n.strip().split(" as ")[0] for n in m.group(2).split(",")],
                ))

        return result
