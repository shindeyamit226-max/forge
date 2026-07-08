"""
TypeScript Parser — extends JavaScript parser with TS-specific features.
Handles: interfaces, type aliases, enums, generics, access modifiers,
decorators, namespaces, modules, declaration files.
"""

from __future__ import annotations

import re
from .javascript_parser import JavaScriptParser
from .base import ParseResult, Symbol, Import, Export, Relationship, Range, Position


class TypeScriptParser(JavaScriptParser):
    """TypeScript parser with full type system support."""

    INTERFACE_PATTERN = re.compile(
        r'^(export\s+)?(?:declare\s+)?interface\s+(\w+)(?:<[^>]*>)?\s*(?:extends\s+([^{]+))?\s*\{',
        re.MULTILINE,
    )

    TYPE_PATTERN = re.compile(
        r'^(export\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=\s*(.+)',
        re.MULTILINE,
    )

    ENUM_PATTERN = re.compile(
        r'^(export\s+)?(?:const\s+)?enum\s+(\w+)\s*\{',
        re.MULTILINE,
    )

    NAMESPACE_PATTERN = re.compile(
        r'^(export\s+)?(?:declare\s+)?namespace\s+(\w+)\s*\{',
        re.MULTILINE,
    )

    ACCESS_MODIFIERS = re.compile(r'\b(public|private|protected|readonly|abstract|static)\b')

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="typescript")

        # Use JS parser for base functionality
        js_result = super().parse(source, filepath)
        result.symbols.extend(js_result.symbols)
        result.imports.extend(js_result.imports)
        result.exports.extend(js_result.exports)
        result.relationships.extend(js_result.relationships)
        result.errors.extend(js_result.errors)

        # Add TS-specific parsing
        self._parse_interfaces(source, result, filepath)
        self._parse_types(source, result, filepath)
        self._parse_enums(source, result, filepath)
        self._parse_namespaces(source, result, filepath)
        self._parse_decorators(source, result, filepath)
        self._enhance_with_types(source, result)

        return result

    def _parse_interfaces(self, source: str, result: ParseResult, filepath: str) -> None:
        for m in self.INTERFACE_PATTERN.finditer(source):
            name = m.group(2)
            extends = [e.strip() for e in m.group(3).split(",")] if m.group(3) else []
            line = source[:m.start()].count('\n') + 1
            is_export = bool(m.group(1))

            # Parse interface body
            body_start = m.end()
            body = self._extract_brace_block(source, body_start)
            properties = self._parse_interface_body(body)

            result.symbols.append(Symbol(
                name=name,
                kind="interface",
                range=self._make_range(line, line + body.count('\n')),
                file=filepath,
                modifiers=["export"] if is_export else [],
                metadata={"extends": extends, "properties": properties},
            ))

    def _parse_types(self, source: str, result: ParseResult, filepath: str) -> None:
        for m in self.TYPE_PATTERN.finditer(source):
            name = m.group(2)
            type_def = m.group(3).strip()
            line = source[:m.start()].count('\n') + 1
            is_export = bool(m.group(1))

            result.symbols.append(Symbol(
                name=name,
                kind="type",
                range=self._make_range(line, line),
                file=filepath,
                return_type=type_def,
                modifiers=["export"] if is_export else [],
            ))

    def _parse_enums(self, source: str, result: ParseResult, filepath: str) -> None:
        for m in self.ENUM_PATTERN.finditer(source):
            name = m.group(2)
            line = source[:m.start()].count('\n') + 1
            is_export = bool(m.group(1))
            is_const = "const enum" in m.group(0)

            body_start = m.end()
            body = self._extract_brace_block(source, body_start)
            members = [l.strip().split("=")[0].strip().rstrip(",") for l in body.splitlines() if l.strip() and not l.strip().startswith("//")]

            result.symbols.append(Symbol(
                name=name,
                kind="enum",
                range=self._make_range(line, line + body.count('\n')),
                file=filepath,
                modifiers=(["export"] if is_export else []) + (["const"] if is_const else []),
                children=[m for m in members if m],
            ))

    def _parse_namespaces(self, source: str, result: ParseResult, filepath: str) -> None:
        for m in self.NAMESPACE_PATTERN.finditer(source):
            name = m.group(2)
            line = source[:m.start()].count('\n') + 1
            is_export = bool(m.group(1))

            result.symbols.append(Symbol(
                name=name,
                kind="namespace",
                range=self._make_range(line, line),
                file=filepath,
                modifiers=["export"] if is_export else [],
            ))

    def _parse_decorators(self, source: str, result: ParseResult, filepath: str) -> None:
        """Parse TypeScript decorators."""
        dec_pattern = re.compile(r'^\s*@(\w+)(?:\(([^)]*)\))?\s*$', re.MULTILINE)
        for m in dec_pattern.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(
                name=m.group(1),
                kind="decorator",
                range=self._make_range(line, line),
                file=filepath,
                metadata={"args": m.group(2) or ""},
            ))

    def _enhance_with_types(self, source: str, result: ParseResult) -> None:
        """Enhance existing symbols with TypeScript type information."""
        lines = source.splitlines()

        for sym in result.symbols:
            if sym.kind in ("function", "method"):
                # Try to extract return type from the signature line
                line_idx = sym.range.start.line - 1
                if 0 <= line_idx < len(lines):
                    line = lines[line_idx]
                    # Match : ReturnType before {
                    ret_match = re.search(r'\)\s*:\s*(\w+(?:<[^>]*>)?(?:\[\])?)\s*\{', line)
                    if ret_match and not sym.return_type:
                        sym.return_type = ret_match.group(1)

    def _extract_brace_block(self, source: str, start: int) -> str:
        """Extract content between matching braces."""
        depth = 1
        i = start
        while i < len(source) and depth > 0:
            if source[i] == '{':
                depth += 1
            elif source[i] == '}':
                depth -= 1
            i += 1
        return source[start:i - 1]

    def _parse_interface_body(self, body: str) -> list[dict]:
        """Parse interface body into properties."""
        properties = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue

            # property: type;
            m = re.match(r'(\w+)\??\s*:\s*(.+?)\s*;?', line)
            if m:
                properties.append({
                    "name": m.group(1),
                    "type": m.group(2).rstrip(";"),
                    "optional": "?" in line.split(":")[0],
                })

        return properties
