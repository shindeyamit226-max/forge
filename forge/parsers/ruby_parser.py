"""Ruby Parser — structural parsing for Ruby source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Range

class RubyParser(BaseParser):
    """Ruby language parser."""
    CLASS_PATTERN = re.compile(r'^class\s+(\w+)(?:\s*<\s*(\w+))?\s*$', re.MULTILINE)
    MODULE_PATTERN = re.compile(r'^module\s+(\w+)', re.MULTILINE)
    DEF_PATTERN = re.compile(r'^\s*(def)\s+(?:self\.)?(\w+[!?]?)\s*(?:\(([^)]*)\))?', re.MULTILINE)
    INCLUDE_PATTERN = re.compile(r'^\s*(?:include|require|require_relative)\s+[\'"]?(\S+?)[\'"]?\s*$', re.MULTILINE)
    ATTR_PATTERN = re.compile(r'^\s*(attr_reader|attr_writer|attr_accessor)\s+(.+)', re.MULTILINE)
    CONST_PATTERN = re.compile(r'^([A-Z]\w*)\s*=', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="ruby")
        # Requires
        for m in self.INCLUDE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(Import(module=m.group(1), range=self._make_range(line, line), kind="require"))
        # Modules
        for m in self.MODULE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="module", range=self._make_range(line, line), file=filepath))
        # Classes
        for m in self.CLASS_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="class", range=self._make_range(line, line),
                file=filepath, metadata={"superclass": m.group(2) or ""}))
        # Methods
        for m in self.DEF_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="function", range=self._make_range(line, line),
                file=filepath, signature=f"def {m.group(2)}({m.group(3) or ''})"))
        # Constants
        for m in self.CONST_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="constant", range=self._make_range(line, line), file=filepath))
        return result
