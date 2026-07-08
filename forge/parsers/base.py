"""
Base parser — abstract interface for all language parsers.
Every parser produces the same structured output: symbols, imports, exports, relationships.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Position:
    line: int
    column: int = 0

    def __str__(self):
        return f"{self.line}:{self.column}"


@dataclass
class Range:
    start: Position
    end: Position

    def __str__(self):
        return f"{self.start}-{self.end}"


@dataclass
class Symbol:
    """A code symbol: function, class, method, variable, type, interface, enum."""
    name: str
    kind: str  # function, class, method, variable, type, interface, enum, constant, decorator, macro
    range: Range
    file: str = ""
    parent: Optional[str] = None  # Parent class/namespace
    signature: str = ""
    return_type: str = ""
    parameters: list[dict] = field(default_factory=list)
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)  # public, private, static, async, etc.
    body_hash: str = ""
    complexity: int = 0  # Cyclomatic complexity
    line_count: int = 0
    children: list[str] = field(default_factory=list)  # Child symbol names
    metadata: dict = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    @property
    def id(self) -> str:
        return f"{self.file}:{self.name}:{self.range.start.line}"


@dataclass
class Import:
    """An import statement."""
    module: str
    names: list[str] = field(default_factory=list)
    alias: str = ""
    is_wildcard: bool = False
    is_relative: bool = False
    range: Range = field(default_factory=lambda: Range(Position(0), Position(0)))
    kind: str = "import"  # import, require, use, include


@dataclass
class Export:
    """An export statement."""
    name: str
    kind: str = "named"  # named, default, all
    range: Range = field(default_factory=lambda: Range(Position(0), Position(0)))


@dataclass
class Relationship:
    """A relationship between symbols."""
    source: str  # symbol id
    target: str  # symbol id or name
    kind: str  # calls, inherits, implements, uses, creates, returns, accepts
    range: Range = field(default_factory=lambda: Range(Position(0), Position(0)))


@dataclass
class ParseResult:
    """Complete parse result for a file."""
    file: str
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    exports: list[Export] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    line_count: int = 0
    complexity: int = 0  # Total file complexity

    @property
    def functions(self) -> list[Symbol]:
        return [s for s in self.symbols if s.kind == "function"]

    @property
    def classes(self) -> list[Symbol]:
        return [s for s in self.symbols if s.kind == "class"]

    @property
    def methods(self) -> list[Symbol]:
        return [s for s in self.symbols if s.kind == "method"]

    @property
    def variables(self) -> list[Symbol]:
        return [s for s in self.symbols if s.kind in ("variable", "constant")]


class BaseParser(ABC):
    """Abstract base for all language parsers."""

    @abstractmethod
    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        """Parse source code and return structured result."""
        ...

    def parse_file(self, filepath: str) -> ParseResult:
        """Parse a file from disk."""
        path = Path(filepath)
        if not path.exists():
            return ParseResult(file=filepath, language="unknown", errors=["File not found"])

        try:
            source = path.read_text(errors="replace")
            result = self.parse(source, filepath)
            result.line_count = len(source.splitlines())
            return result
        except Exception as e:
            return ParseResult(file=filepath, language="unknown", errors=[str(e)])

    def _make_range(self, start_line: int, end_line: int, start_col: int = 0, end_col: int = 0) -> Range:
        return Range(Position(start_line, start_col), Position(end_line, end_col))

    def _compute_complexity(self, source: str) -> int:
        """Estimate cyclomatic complexity from control flow keywords."""
        import re
        keywords = r'\b(if|elif|else|for|while|case|catch|except|&&|\|\||\?)\b'
        return len(re.findall(keywords, source)) + 1

    def _compute_body_hash(self, body: str) -> str:
        import hashlib
        return hashlib.md5(body.encode()).hexdigest()[:12]
