"""Markdown Parser — structural parsing for Markdown files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Range

class MarkdownParser(BaseParser):
    """Markdown parser."""
    HEADING_PATTERN = re.compile(r'^(#{1,6})\s+(.+)', re.MULTILINE)
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)', re.MULTILINE)
    CODE_BLOCK_PATTERN = re.compile(r'^```(\w+)?\s*$', re.MULTILINE)
    IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="markdown")
        for m in self.HEADING_PATTERN.finditer(source):
            level = len(m.group(1))
            title = m.group(2).strip()
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=title, kind=f"heading_{level}", range=self._make_range(line, line), file=filepath))
        for m in self.LINK_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="link", range=self._make_range(line, line),
                file=filepath, metadata={"url": m.group(2)}))
        for m in self.IMAGE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1) or "image", kind="image", range=self._make_range(line, line),
                file=filepath, metadata={"url": m.group(2)}))
        return result
