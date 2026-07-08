"""Kotlin Parser — structural parsing for Kotlin source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Range

class KotlinParser(BaseParser):
    """Kotlin language parser."""
    CLASS_PATTERN = re.compile(r'^(?:data\s+|sealed\s+|abstract\s+|open\s+)?class\s+(\w+)(?:<[^>]*>)?\s*(?:\(([^)]*)\))?\s*(?::\s*([^{]+))?\s*\{?', re.MULTILINE)
    FUN_PATTERN = re.compile(r'^\s*(?:suspend\s+)?(?:inline\s+)?fun\s+(?:<[^>]*>\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*(\S+))?', re.MULTILINE)
    VAL_PATTERN = re.compile(r'^\s*(?:val|var)\s+(\w+)\s*:\s*(\S+)', re.MULTILINE)
    OBJECT_PATTERN = re.compile(r'^object\s+(\w+)(?:\s*:\s*([^{]+))?\s*\{', re.MULTILINE)
    INTERFACE_PATTERN = re.compile(r'^interface\s+(\w+)(?:<[^>]*>)?\s*\{', re.MULTILINE)
    IMPORT_PATTERN = re.compile(r'^import\s+([\w.]+)', re.MULTILINE)
    ANNOTATION_PATTERN = re.compile(r'^@(\w+)', re.MULTILINE)
    COMPANION_PATTERN = re.compile(r'^\s+companion\s+object\s*\{', re.MULTILINE)
    EXTENSION_PATTERN = re.compile(r'^fun\s+(\w+)\.(\w+)\s*\(([^)]*)\)\s*(?::\s*(\S+))?', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="kotlin")
        for m in self.IMPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(Import(module=m.group(1), range=self._make_range(line, line), kind="import"))
        for m in self.ANNOTATION_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="annotation", range=self._make_range(line, line), file=filepath))
        for pattern, kind in [(self.INTERFACE_PATTERN, "interface"), (self.OBJECT_PATTERN, "object"), (self.CLASS_PATTERN, "class")]:
            for m in pattern.finditer(source):
                line = source[:m.start()].count('\n') + 1
                result.symbols.append(Symbol(name=m.group(1), kind=kind, range=self._make_range(line, line), file=filepath))
        for m in self.FUN_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="function", range=self._make_range(line, line),
                file=filepath, return_type=m.group(3) or ""))
        for m in self.VAL_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="property", range=self._make_range(line, line),
                file=filepath, return_type=m.group(2)))
        return result
