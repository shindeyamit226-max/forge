"""
AST-Aware Code Editor — understands code structure, not just text.
Supports Python, JavaScript, TypeScript, Go, Rust, Java.

Key capabilities:
- Find functions, classes, methods by name
- Insert code at structurally correct positions
- Replace function/class bodies
- Extract functions
- Rename symbols across files
- Add imports intelligently
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CodeSymbol:
    """A symbol in the codebase (function, class, method, variable)."""
    name: str
    kind: str  # function, class, method, variable, import
    file: str
    line: int
    end_line: int
    col: int = 0
    parent: Optional[str] = None  # Parent class for methods
    params: list[str] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    body_hash: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    def __str__(self) -> str:
        prefix = f"{self.parent}." if self.parent else ""
        return f"{self.kind} {prefix}{self.name} @ {self.file}:{self.line}"


@dataclass
class EditOperation:
    """A structured edit operation."""
    kind: str  # insert, replace, delete, rename
    file: str
    line: int
    end_line: Optional[int] = None
    content: Optional[str] = None
    symbol_name: Optional[str] = None
    new_name: Optional[str] = None


class PythonASTParser:
    """Parse Python files into structured symbols."""

    def parse(self, source: str, filepath: str = "<string>") -> list[CodeSymbol]:
        """Parse Python source and extract all symbols."""
        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return []

        symbols = []
        self._visit_node(tree, symbols, filepath, parent=None)
        return symbols

    def _visit_node(self, node, symbols, filepath, parent):
        """Recursively visit AST nodes."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef) or isinstance(child, ast.AsyncFunctionDef):
                symbol = self._make_function_symbol(child, filepath, parent)
                symbols.append(symbol)
                # Recurse into nested functions
                self._visit_node(child, symbols, filepath, parent=child.name)

            elif isinstance(child, ast.ClassDef):
                symbol = self._make_class_symbol(child, filepath)
                symbols.append(symbol)
                # Recurse into class methods
                self._visit_node(child, symbols, filepath, parent=child.name)

            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        symbols.append(CodeSymbol(
                            name=target.id,
                            kind="variable",
                            file=filepath,
                            line=child.lineno,
                            end_line=child.end_lineno or child.lineno,
                            col=child.col_offset,
                            parent=parent,
                        ))

            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    name = alias.asname or alias.name
                    symbols.append(CodeSymbol(
                        name=name,
                        kind="import",
                        file=filepath,
                        line=child.lineno,
                        end_line=child.end_lineno or child.lineno,
                        col=child.col_offset,
                    ))

    def _make_function_symbol(self, node, filepath, parent) -> CodeSymbol:
        """Create a CodeSymbol from a function AST node."""
        params = []
        for arg in node.args.args:
            params.append(arg.arg)

        return_type = None
        if node.returns:
            try:
                return_type = ast.unparse(node.returns)
            except Exception:
                pass

        docstring = ast.get_docstring(node)
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(f"@{ast.unparse(dec)}")
            except Exception:
                decorators.append("@?")

        return CodeSymbol(
            name=node.name,
            kind="method" if parent else "function",
            file=filepath,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            col=node.col_offset,
            parent=parent,
            params=params,
            return_type=return_type,
            docstring=docstring,
            decorators=decorators,
        )

    def _make_class_symbol(self, node, filepath) -> CodeSymbol:
        """Create a CodeSymbol from a class AST node."""
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                pass

        docstring = ast.get_docstring(node)
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(f"@{ast.unparse(dec)}")
            except Exception:
                decorators.append("@?")

        return CodeSymbol(
            name=node.name,
            kind="class",
            file=filepath,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            col=node.col_offset,
            docstring=docstring,
            decorators=decorators,
        )

    def find_symbol(self, source: str, name: str, filepath: str = "<string>") -> Optional[CodeSymbol]:
        """Find a specific symbol by name."""
        symbols = self.parse(source, filepath)
        for sym in symbols:
            if sym.name == name or sym.qualified_name == name:
                return sym
        return None

    def get_function_body(self, source: str, func_name: str) -> Optional[str]:
        """Extract the body of a function."""
        lines = source.splitlines()
        symbol = self.find_symbol(source, func_name)
        if not symbol:
            return None

        # Get lines from def to end (dedented)
        body_lines = lines[symbol.line - 1:symbol.end_line]
        return "\n".join(body_lines)

    def replace_function_body(self, source: str, func_name: str, new_body: str) -> Optional[str]:
        """Replace a function's body with new code, preserving indentation."""
        lines = source.splitlines()
        symbol = self.find_symbol(source, func_name)
        if not symbol:
            return None

        # Determine indentation of the function
        func_line = lines[symbol.line - 1]
        indent = len(func_line) - len(func_line.lstrip())

        # Indent the new body
        indented_body = textwrap.indent(new_body, " " * (indent + 4))
        if not indented_body.endswith("\n"):
            indented_body += "\n"

        # Replace lines
        new_lines = lines[:symbol.line] + indented_body.splitlines() + lines[symbol.end_line:]
        return "\n".join(new_lines)

    def add_import(self, source: str, import_line: str) -> str:
        """Add an import statement at the correct position."""
        lines = source.splitlines()

        # Find the last import line
        last_import = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                last_import = i

        # Check if import already exists
        if import_line.strip() in source:
            return source

        # Insert after last import
        if last_import > 0:
            lines.insert(last_import + 1, import_line)
        else:
            # Insert at top (after any comments/docstrings)
            insert_at = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                    insert_at = i + 1
                else:
                    break
            lines.insert(insert_at, import_line)

        return "\n".join(lines)

    def extract_function(
        self, source: str, start_line: int, end_line: int, func_name: str
    ) -> tuple[str, str]:
        """Extract lines into a new function. Returns (modified_source, new_function)."""
        lines = source.splitlines()
        extracted = lines[start_line - 1:end_line]

        # Determine common indentation
        min_indent = float("inf")
        for line in extracted:
            if line.strip():
                min_indent = min(min_indent, len(line) - len(line.lstrip()))
        min_indent = int(min_indent) if min_indent != float("inf") else 0

        # Dedent extracted code
        dedented = []
        for line in extracted:
            if line.strip():
                dedented.append(line[min_indent:])
            else:
                dedented.append("")

        body = "\n".join(dedented)

        # Create the new function
        new_func = f"def {func_name}():\n{textwrap.indent(body, '    ')}"

        # Replace original lines with a call
        call_line = f"{' ' * min_indent}{func_name}()"
        new_lines = lines[:start_line - 1] + [call_line] + lines[end_line:]

        return "\n".join(new_lines), new_func


class JavaScriptASTParser:
    """Regex-based parser for JavaScript/TypeScript (no AST dependency)."""

    FUNC_PATTERNS = [
        # function name(params) {
        re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)'),
        # const name = (params) => {
        re.compile(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>'),
        # const name = function(params) {
        re.compile(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)'),
    ]

    CLASS_PATTERN = re.compile(r'^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)')
    METHOD_PATTERN = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\(([^)]*)\)')

    def parse(self, source: str, filepath: str = "<string>") -> list[CodeSymbol]:
        symbols = []
        lines = source.splitlines()
        current_class = None

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Class
            m = self.CLASS_PATTERN.match(stripped)
            if m:
                current_class = m.group(1)
                symbols.append(CodeSymbol(
                    name=current_class, kind="class",
                    file=filepath, line=i, end_line=i,
                ))
                continue

            # Functions
            for pattern in self.FUNC_PATTERNS:
                m = pattern.match(stripped)
                if m:
                    symbols.append(CodeSymbol(
                        name=m.group(1), kind="function",
                        file=filepath, line=i, end_line=i,
                        params=[p.strip().split(":")[0].strip() for p in m.group(2).split(",") if p.strip()],
                        parent=current_class,
                    ))
                    break

            # Methods (inside class)
            if current_class and not stripped.startswith(("function", "const", "let", "var", "//", "/*")):
                m = self.METHOD_PATTERN.match(line)
                if m and m.group(1) not in ("if", "for", "while", "switch", "catch"):
                    symbols.append(CodeSymbol(
                        name=m.group(1), kind="method",
                        file=filepath, line=i, end_line=i,
                        parent=current_class,
                        params=[p.strip().split(":")[0].strip() for p in m.group(2).split(",") if p.strip()],
                    ))

            # Reset class context on closing brace at column 0
            if stripped == "}" and not line.startswith(" ") and not line.startswith("\t"):
                current_class = None

        return symbols


class GoASTParser:
    """Regex-based Go parser."""

    FUNC_PATTERN = re.compile(r'^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)')

    def parse(self, source: str, filepath: str = "<string>") -> list[CodeSymbol]:
        symbols = []
        for i, line in enumerate(source.splitlines(), 1):
            m = self.FUNC_PATTERN.match(line.strip())
            if m:
                symbols.append(CodeSymbol(
                    name=m.group(1), kind="function",
                    file=filepath, line=i, end_line=i,
                ))
        return symbols


class RustASTParser:
    """Regex-based Rust parser."""

    FUNC_PATTERN = re.compile(r'^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)')

    def parse(self, source: str, filepath: str = "<string>") -> list[CodeSymbol]:
        symbols = []
        for i, line in enumerate(source.splitlines(), 1):
            m = self.FUNC_PATTERN.match(line.strip())
            if m:
                symbols.append(CodeSymbol(
                    name=m.group(1), kind="function",
                    file=filepath, line=i, end_line=i,
                ))
        return symbols


# Registry of parsers
_PARSERS = {
    ".py": PythonASTParser(),
    ".js": JavaScriptASTParser(),
    ".jsx": JavaScriptASTParser(),
    ".ts": JavaScriptASTParser(),
    ".tsx": JavaScriptASTParser(),
    ".go": GoASTParser(),
    ".rs": RustASTParser(),
}


def get_parser(filepath: str):
    """Get the appropriate parser for a file."""
    ext = Path(filepath).suffix.lower()
    return _PARSERS.get(ext)


def parse_file(filepath: str) -> list[CodeSymbol]:
    """Parse a file and return its symbols."""
    path = Path(filepath)
    if not path.exists():
        return []

    parser = get_parser(filepath)
    if not parser:
        return []

    try:
        source = path.read_text(errors="replace")
        return parser.parse(source, filepath)
    except Exception:
        return []


def find_symbol_in_project(root: str, name: str) -> list[CodeSymbol]:
    """Search for a symbol across the entire project."""
    from .context import ProjectContext, IGNORE_DIRS

    results = []
    for dirpath, dirnames, filenames in __import__("os").walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fname in filenames:
            fpath = str(Path(dirpath) / fname)
            parser = get_parser(fpath)
            if not parser:
                continue
            try:
                source = Path(fpath).read_text(errors="replace")
                sym = parser.find_symbol(source, name, fpath)
                if sym:
                    results.append(sym)
            except Exception:
                continue

    return results
