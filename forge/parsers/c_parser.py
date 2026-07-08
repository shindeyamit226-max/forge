"""C Parser — structural parsing for C source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Relationship, Range

class CParser(BaseParser):
    """C language parser."""
    FUNC_PATTERN = re.compile(r'^(?:(static|extern|inline|const)\s+)*(\w+(?:\s*\*)*)\s+(\w+)\s*\(([^)]*)\)\s*\{', re.MULTILINE)
    STRUCT_PATTERN = re.compile(r'^(?:typedef\s+)?struct\s+(\w*)\s*\{', re.MULTILINE)
    ENUM_PATTERN = re.compile(r'^(?:typedef\s+)?enum\s+(\w*)\s*\{', re.MULTILINE)
    TYPEDEF_PATTERN = re.compile(r'^typedef\s+(.+?)\s+(\w+)\s*;', re.MULTILINE)
    INCLUDE_PATTERN = re.compile(r'#include\s+[<"]([^>"]+)[>"]', re.MULTILINE)
    DEFINE_PATTERN = re.compile(r'#define\s+(\w+)(?:\(([^)]*)\))?\s*(.*)', re.MULTILINE)
    UNION_PATTERN = re.compile(r'^(?:typedef\s+)?union\s+(\w*)\s*\{', re.MULTILINE)
    GLOBAL_PATTERN = re.compile(r'^(?:extern\s+)?(\w+(?:\s*\*)*)\s+(\w+)\s*(?:=\s*[^;]+)?;', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="c")
        # Includes
        for m in self.INCLUDE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.imports.append(__import__('forge.parsers.base', fromlist=['Import']).Import(
                module=m.group(1), range=self._make_range(line, line), kind="include"))
        # Defines
        for m in self.DEFINE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="macro", range=self._make_range(line, line),
                file=filepath, metadata={"params": m.group(2), "body": m.group(3).strip()}))
        # Structs
        for m in self.STRUCT_PATTERN.finditer(source):
            name = m.group(1) or f"anon_struct_{m.start()}"
            line = source[:m.start()].count('\n') + 1
            body = self._extract_block(source, m.end())
            fields = self._parse_c_fields(body)
            result.symbols.append(Symbol(name=name, kind="struct", range=self._make_range(line, line),
                file=filepath, metadata={"fields": fields}))
        # Enums
        for m in self.ENUM_PATTERN.finditer(source):
            name = m.group(1) or f"anon_enum_{m.start()}"
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=name, kind="enum", range=self._make_range(line, line), file=filepath))
        # Typedefs
        for m in self.TYPEDEF_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="type", range=self._make_range(line, line),
                file=filepath, return_type=m.group(1)))
        # Functions
        for m in self.FUNC_PATTERN.finditer(source):
            name = m.group(3)
            return_type = m.group(2)
            params = m.group(4)
            line = source[:m.start()].count('\n') + 1
            modifiers = [m.group(1)] if m.group(1) else []
            result.symbols.append(Symbol(name=name, kind="function", range=self._make_range(line, line),
                file=filepath, return_type=return_type, modifiers=modifiers,
                parameters=self._parse_c_params(params), signature=f"{return_type} {name}({params})"))
        return result
    def _extract_block(self, source, start):
        depth, i = 1, start
        while i < len(source) and depth > 0:
            if source[i] == '{': depth += 1
            elif source[i] == '}': depth -= 1
            i += 1
        return source[start:i-1]
    def _parse_c_fields(self, body):
        fields = []
        for line in body.splitlines():
            line = line.strip().rstrip(';')
            if not line or line.startswith('//') or line.startswith('/*'): continue
            parts = line.rsplit(None, 1)
            if len(parts) == 2:
                fields.append({"type": parts[0], "name": parts[1]})
        return fields
    def _parse_c_params(self, params_str):
        if not params_str.strip() or params_str.strip() == 'void': return []
        params = []
        for p in params_str.split(','):
            p = p.strip()
            if not p: continue
            parts = p.rsplit(None, 1)
            if len(parts) == 2: params.append({"type": parts[0], "name": parts[1]})
            elif len(parts) == 1: params.append({"type": parts[0]})
        return params
