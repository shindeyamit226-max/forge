"""Scala Parser — structural parsing for Scala source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Range

class ScalaParser(BaseParser):
    """Scala language parser."""
    CLASS_PATTERN = re.compile(r'^(?:case\s+|abstract\s+|sealed\s+)?class\s+(\w+)(?:\[([^\]]*)\])?\s*(?:\(([^)]*)\))?\s*(?:extends\s+(\w+))?', re.MULTILINE)
    OBJECT_PATTERN = re.compile(r'^object\s+(\w+)(?:\s+extends\s+(\w+))?', re.MULTILINE)
    TRAIT_PATTERN = re.compile(r'^(?:sealed\s+)?trait\s+(\w+)(?:\[([^\]]*)\])?', re.MULTILINE)
    DEF_PATTERN = re.compile(r'^\s*(?:override\s+)?def\s+(\w+)(?:\[([^\]]*)\])?\s*\(([^)]*)\)\s*(?::\s*(\S+))?\s*=', re.MULTILINE)
    VAL_PATTERN = re.compile(r'^\s*(?:lazy\s+)?(?:val|var)\s+(\w+)\s*:\s*(\S+)', re.MULTILINE)
    IMPORT_PATTERN = re.compile(r'^import\s+([\w.]+(?:\._|\.\{[^}]+\})?)', re.MULTILINE)
    PACKAGE_PATTERN = re.compile(r'^package\s+([\w.]+)', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="scala")
        for m in self.PACKAGE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="package", range=self._make_range(line, line), file=filepath))
        for m in self.IMPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(Import(module=m.group(1), range=self._make_range(line, line), kind="import"))
        for pattern, kind in [(self.TRAIT_PATTERN, "trait"), (self.OBJECT_PATTERN, "object"), (self.CLASS_PATTERN, "class")]:
            for m in pattern.finditer(source):
                line = source[:m.start()].count('\n') + 1
                result.symbols.append(Symbol(name=m.group(1), kind=kind, range=self._make_range(line, line), file=filepath))
        for m in self.DEF_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="function", range=self._make_range(line, line),
                file=filepath, return_type=m.group(4) or ""))
        for m in self.VAL_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="property", range=self._make_range(line, line),
                file=filepath, return_type=m.group(2)))
        return result
