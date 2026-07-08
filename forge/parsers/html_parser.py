"""HTML Parser — structural parsing for HTML files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Range

class HtmlParser(BaseParser):
    """HTML parser."""
    TAG_PATTERN = re.compile(r'<(\w+)(?:\s+id=[\'"](\w+)[\'"])?(?:\s+class=[\'"]([^\'"]+)[\'"])?', re.MULTILINE)
    SCRIPT_PATTERN = re.compile(r'<script(?:\s+src=[\'"]([^\'"]+)[\'"])?', re.MULTILINE)
    STYLE_PATTERN = re.compile(r'<style', re.MULTILINE)
    LINK_PATTERN = re.compile(r'<link\s+[^>]*href=[\'"]([^\'"]+)[\'"]', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="html")
        for m in self.SCRIPT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            if m.group(1):
                result.imports.append(__import__('forge.parsers.base', fromlist=['Import']).Import(
                    module=m.group(1), range=self._make_range(line, line), kind="script"))
        for m in self.TAG_PATTERN.finditer(source):
            tag, id_attr, class_attr = m.group(1), m.group(2), m.group(3)
            line = source[:m.start()].count('\n') + 1
            if id_attr:
                result.symbols.append(Symbol(name=id_attr, kind="element", range=self._make_range(line, line),
                    file=filepath, metadata={"tag": tag, "class": class_attr or ""}))
        return result
