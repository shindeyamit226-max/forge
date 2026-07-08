"""CSS Parser — structural parsing for CSS/SCSS/Less files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Range

class CssParser(BaseParser):
    """CSS/SCSS/Less parser."""
    SELECTOR_PATTERN = re.compile(r'^([.#]?\w[\w\-.*#>[\]=:~+]*)\s*\{', re.MULTILINE)
    VAR_PATTERN = re.compile(r'^--(\w[\w-]*)\s*:', re.MULTILINE)
    SCSS_VAR_PATTERN = re.compile(r'^\$(\w[\w-]*)\s*:', re.MULTILINE)
    MIXIN_PATTERN = re.compile(r'^@mixin\s+(\w+)', re.MULTILINE)
    IMPORT_PATTERN = re.compile(r'^@import\s+[\'"]([^\'"]+)[\'"]', re.MULTILINE)
    MEDIA_PATTERN = re.compile(r'^@media\s+([^{]+)\{', re.MULTILINE)
    KEYFRAME_PATTERN = re.compile(r'^@keyframes\s+(\w+)', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="css")
        for m in self.IMPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(__import__('forge.parsers.base', fromlist=['Import']).Import(
                module=m.group(1), range=self._make_range(line, line), kind="import"))
        for m in self.SELECTOR_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="selector", range=self._make_range(line, line), file=filepath))
        for m in self.KEYFRAME_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="keyframe", range=self._make_range(line, line), file=filepath))
        for m in self.MIXIN_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="mixin", range=self._make_range(line, line), file=filepath))
        for m in self.VAR_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="variable", range=self._make_range(line, line), file=filepath))
        return result
