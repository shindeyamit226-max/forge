"""Go Parser — structural parsing for Go source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Export, Relationship, Range, Position

class GoParser(BaseParser):
    """Go language parser."""
    FUNC_PATTERN = re.compile(r'^func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*\(([^)]*)\)\s*(?:\(([^)]*)\)|(\S+))?\s*\{?', re.MULTILINE)
    TYPE_PATTERN = re.compile(r'^type\s+(\w+)\s+(struct|interface)\s*\{', re.MULTILINE)
    IMPORT_PATTERN = re.compile(r'(?:import\s+"([^"]+)"|import\s+\(\s*(.*?)\s*\))', re.MULTILINE | re.DOTALL)
    VAR_PATTERN = re.compile(r'^(?:var|const)\s+(\w+)\s+(\S+)', re.MULTILINE)
    METHOD_PATTERN = re.compile(r'^func\s+\((\w+)\s+\*?(\w+)\)\s+(\w+)\s*\(([^)]*)\)\s*(?:\(([^)]*)\)|(\S+))?\s*\{?', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="go")
        lines = source.splitlines()

        # Imports
        for m in self.IMPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            if m.group(1):
                result.imports.append(Import(module=m.group(1), range=self._make_range(line, line), kind="import"))
            elif m.group(2):
                for imp in re.findall(r'"([^"]+)"', m.group(2)):
                    result.imports.append(Import(module=imp, range=self._make_range(line, line), kind="import"))

        # Types (structs and interfaces)
        for m in self.TYPE_PATTERN.finditer(source):
            name, kind = m.group(1), m.group(2)
            line = source[:m.start()].count('\n') + 1
            body_start = m.end()
            body = self._extract_block(source, body_start)
            fields = self._parse_struct_fields(body) if kind == "struct" else self._parse_interface_methods(body)
            result.symbols.append(Symbol(name=name, kind=kind, range=self._make_range(line, line + body.count('\n')),
                file=filepath, metadata={"fields": fields}))

        # Methods (with receivers)
        for m in self.METHOD_PATTERN.finditer(source):
            receiver, recv_type, name = m.group(1), m.group(2), m.group(3)
            params = m.group(4)
            returns = m.group(5) or m.group(6) or ""
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=name, kind="method", range=self._make_range(line, line),
                file=filepath, parent=recv_type, parameters=self._parse_go_params(params),
                return_type=returns, signature=f"func ({receiver} *{recv_type}) {name}({params}) {returns}"))

        # Functions
        for m in self.FUNC_PATTERN.finditer(source):
            if m.group(2): continue  # Skip methods (already parsed)
            name = m.group(3)
            params = m.group(4)
            returns = m.group(5) or m.group(6) or ""
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=name, kind="function", range=self._make_range(line, line),
                file=filepath, parameters=self._parse_go_params(params), return_type=returns,
                signature=f"func {name}({params}) {returns}"))

        # Variables and constants
        for m in self.VAR_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="variable", range=self._make_range(line, line),
                file=filepath, return_type=m.group(2)))

        return result

    def _extract_block(self, source: str, start: int) -> str:
        depth, i = 1, start
        while i < len(source) and depth > 0:
            if source[i] == '{': depth += 1
            elif source[i] == '}': depth -= 1
            i += 1
        return source[start:i-1]

    def _parse_struct_fields(self, body: str) -> list[dict]:
        fields = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith('//'): continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                ftype = parts[1]
                tag = ""
                if '`' in line:
                    tag = line.split('`')[1]
                fields.append({"name": name, "type": ftype, "tag": tag})
        return fields

    def _parse_interface_methods(self, body: str) -> list[dict]:
        methods = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith('//'): continue
            m = re.match(r'(\w+)\s*\(([^)]*)\)\s*(.*)', line)
            if m:
                methods.append({"name": m.group(1), "params": m.group(2), "returns": m.group(3).strip()})
        return methods

    def _parse_go_params(self, params_str: str) -> list[dict]:
        if not params_str.strip(): return []
        params = []
        for p in params_str.split(','):
            p = p.strip()
            if not p: continue
            parts = p.split()
            if len(parts) >= 2:
                params.append({"name": parts[0], "type": parts[1]})
            elif len(parts) == 1:
                params.append({"name": parts[0]})
        return params
