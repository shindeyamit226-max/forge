"""YAML Parser — structural parsing for YAML files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Range

class YamlParser(BaseParser):
    """YAML parser."""
    KEY_PATTERN = re.compile(r'^(\s*)([\w.-]+)\s*:', re.MULTILINE)
    ANCHOR_PATTERN = re.compile(r'^(\w+)\s*:&', re.MULTILINE)
    ALIAS_PATTERN = re.compile(r'\*(\w+)', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="yaml")
        lines = source.splitlines()
        for i, line in enumerate(lines, 1):
            m = self.KEY_PATTERN.match(line)
            if m:
                indent = len(m.group(1))
                key = m.group(2)
                if indent == 0:
                    result.symbols.append(Symbol(name=key, kind="key", range=self._make_range(i, i), file=filepath))
        for m in self.ANCHOR_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="anchor", range=self._make_range(line, line), file=filepath))
        return result
