"""PHP Parser — structural parsing for PHP source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Range

class PhpParser(BaseParser):
    """PHP language parser."""
    CLASS_PATTERN = re.compile(r'^\s*(?:abstract\s+|final\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?\s*\{', re.MULTILINE)
    INTERFACE_PATTERN = re.compile(r'^\s*interface\s+(\w+)\s*\{', re.MULTILINE)
    TRAIT_PATTERN = re.compile(r'^\s*trait\s+(\w+)\s*\{', re.MULTILINE)
    FUNCTION_PATTERN = re.compile(r'^\s*(?:public|protected|private)?\s*(?:static\s+)?(?:abstract\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*(\??\w+))?', re.MULTILINE)
    NAMESPACE_PATTERN = re.compile(r'^namespace\s+([\w\\]+)\s*;', re.MULTILINE)
    USE_PATTERN = re.compile(r'^use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;', re.MULTILINE)
    CONST_PATTERN = re.compile(r'^\s*(?:public\s+)?const\s+(\w+)\s*=', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="php")
        # Namespace
        for m in self.NAMESPACE_PATTERN.finditer(source):
            result.symbols.append(Symbol(name=m.group(1), kind="namespace", range=self._make_range(1, 1), file=filepath))
        # Use statements
        for m in self.USE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(Import(module=m.group(1), alias=m.group(2) or "", range=self._make_range(line, line), kind="use"))
        # Interfaces
        for m in self.INTERFACE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="interface", range=self._make_range(line, line), file=filepath))
        # Traits
        for m in self.TRAIT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="trait", range=self._make_range(line, line), file=filepath))
        # Classes
        for m in self.CLASS_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="class", range=self._make_range(line, line),
                file=filepath, metadata={"extends": m.group(2) or "", "implements": m.group(3) or ""}))
        # Functions/Methods
        for m in self.FUNCTION_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="function", range=self._make_range(line, line),
                file=filepath, return_type=m.group(3) or ""))
        return result
