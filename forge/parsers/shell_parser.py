"""Shell Parser — structural parsing for shell scripts."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Range

class ShellParser(BaseParser):
    """Shell/Bash script parser."""
    FUNC_PATTERN = re.compile(r'^(\w+)\s*\(\)\s*\{|^function\s+(\w+)\s*(?:\(\))?\s*\{', re.MULTILINE)
    ALIAS_PATTERN = re.compile(r'^alias\s+(\w+)=', re.MULTILINE)
    EXPORT_PATTERN = re.compile(r'^export\s+(\w+)=', re.MULTILINE)
    SOURCE_PATTERN = re.compile(r'^source\s+[\'"]?([^\'"\s]+)[\'"]?|^\.\s+[\'"]?([^\'"\s]+)[\'"]?', re.MULTILINE)
    VARIABLE_PATTERN = re.compile(r'^(\w+)=', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="shell")
        for m in self.SOURCE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            module = m.group(1) or m.group(2)
            result.imports.append(Import(module=module, range=self._make_range(line, line), kind="source"))
        for m in self.FUNC_PATTERN.finditer(source):
            name = m.group(1) or m.group(2)
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=name, kind="function", range=self._make_range(line, line), file=filepath))
        for m in self.ALIAS_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="alias", range=self._make_range(line, line), file=filepath))
        for m in self.EXPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="variable", range=self._make_range(line, line), file=filepath, modifiers=["exported"]))
        return result
