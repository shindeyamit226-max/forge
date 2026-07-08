"""Swift Parser — structural parsing for Swift source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Range

class SwiftParser(BaseParser):
    """Swift language parser."""
    CLASS_PATTERN = re.compile(r'^(?:public\s+|open\s+|internal\s+)?(?:final\s+)?class\s+(\w+)(?:<[^>]*>)?\s*:\s*([^{]+)\s*\{', re.MULTILINE)
    STRUCT_PATTERN = re.compile(r'^(?:public\s+)?struct\s+(\w+)(?:<[^>]*>)?\s*(?::\s*([^{]+))?\s*\{', re.MULTILINE)
    PROTOCOL_PATTERN = re.compile(r'^(?:public\s+)?protocol\s+(\w+)\s*(?::\s*([^{]+))?\s*\{', re.MULTILINE)
    ENUM_PATTERN = re.compile(r'^(?:public\s+)?enum\s+(\w+)(?:<[^>]*>)?\s*(?::\s*([^{]+))?\s*\{', re.MULTILINE)
    FUNC_PATTERN = re.compile(r'^\s+(?:public|private|internal|open|fileprivate)?\s*(?:static\s+)?(?:class\s+)?func\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?:->\s*(\S+))?', re.MULTILINE)
    IMPORT_PATTERN = re.compile(r'^import\s+(\w+)', re.MULTILINE)
    EXTENSION_PATTERN = re.compile(r'^extension\s+(\w+)(?:\s+where\s+[^{]+)?\s*\{', re.MULTILINE)
    PROPERTY_PATTERN = re.compile(r'^\s+(?:public|private|internal)?\s*(?:static\s+)?(?:var|let)\s+(\w+)\s*:\s*(\S+)', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="swift")
        for m in self.IMPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(Import(module=m.group(1), range=self._make_range(line, line), kind="import"))
        for m in self.EXTENSION_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="extension", range=self._make_range(line, line), file=filepath))
        for pattern, kind in [(self.PROTOCOL_PATTERN, "protocol"), (self.ENUM_PATTERN, "enum"),
                              (self.STRUCT_PATTERN, "struct"), (self.CLASS_PATTERN, "class")]:
            for m in pattern.finditer(source):
                line = source[:m.start()].count('\n') + 1
                result.symbols.append(Symbol(name=m.group(1), kind=kind, range=self._make_range(line, line), file=filepath))
        for m in self.FUNC_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="function", range=self._make_range(line, line),
                file=filepath, return_type=m.group(3) or ""))
        for m in self.PROPERTY_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="property", range=self._make_range(line, line),
                file=filepath, return_type=m.group(2)))
        return result
