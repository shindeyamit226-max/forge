"""Rust Parser — structural parsing for Rust source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Export, Relationship, Range, Position

class RustParser(BaseParser):
    """Rust language parser."""
    FN_PATTERN = re.compile(r'^(pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?:->\s*(\S+))?\s*\{?', re.MULTILINE)
    STRUCT_PATTERN = re.compile(r'^(pub\s+)?struct\s+(\w+)(?:<[^>]*>)?\s*(?:\{|;|\()', re.MULTILINE)
    ENUM_PATTERN = re.compile(r'^(pub\s+)?enum\s+(\w+)(?:<[^>]*>)?\s*\{', re.MULTILINE)
    TRAIT_PATTERN = re.compile(r'^(pub\s+)?(?:unsafe\s+)?trait\s+(\w+)(?:<[^>]*>)?\s*(?:where\s+[^{]*)?\{', re.MULTILINE)
    IMPL_PATTERN = re.compile(r'^impl(?:<[^>]*>)?\s+(?:.*\s+for\s+)?(\w+)(?:<[^>]*>)?\s*(?:where\s+[^{]*)?\{', re.MULTILINE)
    USE_PATTERN = re.compile(r'^use\s+([\w:]+(?:\{[^}]+\})?)\s*;', re.MULTILINE)
    CONST_PATTERN = re.compile(r'^(pub\s+)?(?:static|const)\s+(\w+)\s*:\s*(\S+)', re.MULTILINE)
    MACRO_PATTERN = re.compile(r'^macro_rules!\s+(\w+)', re.MULTILINE)
    MOD_PATTERN = re.compile(r'^(pub\s+)?mod\s+(\w+)\s*;', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="rust")

        # Use statements
        for m in self.USE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            module = m.group(1)
            names = re.findall(r'(\w+)', module.split('::')[-1] if '{' not in module else module)
            result.imports.append(Import(module=module, names=names, range=self._make_range(line, line), kind="use"))

        # Modules
        for m in self.MOD_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="module", range=self._make_range(line, line),
                file=filepath, modifiers=["pub"] if m.group(1) else []))

        # Structs
        for m in self.STRUCT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="struct", range=self._make_range(line, line),
                file=filepath, modifiers=["pub"] if m.group(1) else []))

        # Enums
        for m in self.ENUM_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            body = self._extract_block(source, m.end())
            variants = [l.strip().split('(')[0].split('{')[0].strip().rstrip(',') for l in body.splitlines() if l.strip() and not l.strip().startswith('//')]
            result.symbols.append(Symbol(name=m.group(2), kind="enum", range=self._make_range(line, line),
                file=filepath, modifiers=["pub"] if m.group(1) else [], children=[v for v in variants if v]))

        # Traits
        for m in self.TRAIT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="trait", range=self._make_range(line, line),
                file=filepath, modifiers=["pub"] if m.group(1) else []))

        # Impl blocks
        for m in self.IMPL_PATTERN.finditer(source):
            name = m.group(1)
            line = source[:m.start()].count('\n') + 1
            body = self._extract_block(source, m.end())
            # Parse methods within impl
            for fm in self.FN_PATTERN.finditer(body):
                fn_line = line + body[:fm.start()].count('\n')
                result.symbols.append(Symbol(name=fm.group(2), kind="method",
                    range=self._make_range(fn_line, fn_line), file=filepath, parent=name,
                    return_type=(fm.group(4) or "").rstrip('{'), modifiers=["pub"] if fm.group(1) else []))

        # Functions (top-level)
        for m in self.FN_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            # Skip if inside impl block (already parsed)
            if not any(s.range.start.line <= line <= s.range.end.line and s.kind in ("struct", "trait") for s in result.symbols):
                result.symbols.append(Symbol(name=m.group(2), kind="function",
                    range=self._make_range(line, line), file=filepath,
                    return_type=(m.group(4) or "").rstrip('{'), modifiers=["pub"] if m.group(1) else []))

        # Constants and statics
        for m in self.CONST_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="constant", range=self._make_range(line, line),
                file=filepath, return_type=m.group(3), modifiers=["pub"] if m.group(1) else []))

        # Macros
        for m in self.MACRO_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="macro", range=self._make_range(line, line), file=filepath))

        return result

    def _extract_block(self, source: str, start: int) -> str:
        depth, i = 1, start
        while i < len(source) and depth > 0:
            if source[i] == '{': depth += 1
            elif source[i] == '}': depth -= 1
            i += 1
        return source[start:i-1]
