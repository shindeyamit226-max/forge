"""
JavaScript Parser — regex-based structural parsing for JS/JSX.
Extracts: functions, classes, methods, imports, exports, arrow functions,
destructuring, template literals, and call relationships.
"""

from __future__ import annotations

import re
from typing import Optional
from .base import BaseParser, ParseResult, Symbol, Import, Export, Relationship, Range, Position


class JavaScriptParser(BaseParser):
    """JavaScript/JSX parser using regex patterns."""

    FUNC_PATTERNS = [
        # function declaration
        re.compile(r'^(export\s+)?(?:default\s+)?(async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?::\s*(\S+))?\s*\{?', re.MULTILINE),
        # const/let/var arrow function
        re.compile(r'^(export\s+)?(?:default\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?(?:<[^>]*>)?\(([^)]*)\)\s*(?::\s*(\S+))?\s*=>', re.MULTILINE),
        # const/let/var function expression
        re.compile(r'^(export\s+)?(?:default\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?function\s*(?:<[^>]*>)?\s*\(([^)]*)\)', re.MULTILINE),
        # object method shorthand
        re.compile(r'^\s+(async\s+)?(\w+)\s*\(([^)]*)\)\s*\{', re.MULTILINE),
    ]

    CLASS_PATTERN = re.compile(r'^(export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?\s*\{?', re.MULTILINE)

    IMPORT_PATTERNS = [
        # import { x, y } from 'module'
        re.compile(r'import\s+\{([^}]+)\}\s+from\s+[\'"]([^\'"]+)[\'"]'),
        # import x from 'module'
        re.compile(r'import\s+(\w+)\s+from\s+[\'"]([^\'"]+)[\'"]'),
        # import * as x from 'module'
        re.compile(r'import\s+\*\s+as\s+(\w+)\s+from\s+[\'"]([^\'"]+)[\'"]'),
        # import 'module'
        re.compile(r'import\s+[\'"]([^\'"]+)[\'"]'),
        # const x = require('module')
        re.compile(r'(?:const|let|var)\s+(?:\{([^}]+)\}|(\w+))\s*=\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'),
    ]

    EXPORT_PATTERNS = [
        re.compile(r'^export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)'),
        re.compile(r'^export\s+\{([^}]+)\}'),
        re.compile(r'^export\s+default\s+(\w+)'),
    ]

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="javascript")
        lines = source.splitlines()

        self._parse_imports(source, result, filepath)
        self._parse_exports(source, result, filepath)
        self._parse_classes(source, result, filepath, lines)
        self._parse_functions(source, result, filepath, lines)
        self._parse_variables(source, result, filepath)
        self._parse_calls(source, result, filepath)

        return result

    def _parse_imports(self, source: str, result: ParseResult, filepath: str) -> None:
        for pattern in self.IMPORT_PATTERNS:
            for m in pattern.finditer(source):
                groups = m.groups()
                line = source[:m.start()].count('\n') + 1

                if len(groups) == 2:
                    # import { x } from 'mod' or import x from 'mod'
                    names_str = groups[0]
                    module = groups[1]
                    if names_str:
                        names = [n.strip().split(" as ")[0].strip() for n in names_str.split(",")]
                    else:
                        names = []
                    result.imports.append(Import(
                        module=module, names=names,
                        range=self._make_range(line, line),
                        kind="import",
                    ))
                elif len(groups) == 3:
                    # require destructured or simple
                    names_str, single, module = groups
                    if names_str:
                        names = [n.strip().split(" as ")[0].strip() for n in names_str.split(",")]
                    elif single:
                        names = [single]
                    else:
                        names = []
                    result.imports.append(Import(
                        module=module, names=names,
                        range=self._make_range(line, line),
                        kind="require",
                    ))
                elif len(groups) == 1:
                    # import 'module'
                    result.imports.append(Import(
                        module=groups[0], names=[],
                        range=self._make_range(line, line),
                        kind="import_side_effect",
                    ))

    def _parse_exports(self, source: str, result: ParseResult, filepath: str) -> None:
        for pattern in self.EXPORT_PATTERNS:
            for m in pattern.finditer(source):
                line = source[:m.start()].count('\n') + 1
                names = m.group(1)
                if names:
                    for name in names.split(","):
                        name = name.strip().split(" as ")[0].strip()
                        if name:
                            result.exports.append(Export(
                                name=name,
                                kind="named",
                                range=self._make_range(line, line),
                            ))

    def _parse_classes(self, source: str, result: ParseResult, filepath: str, lines: list) -> None:
        for m in self.CLASS_PATTERN.finditer(source):
            name = m.group(2)
            extends = m.group(3) or ""
            implements = [i.strip() for i in m.group(4).split(",")] if m.group(4) else []
            line = source[:m.start()].count('\n') + 1

            result.symbols.append(Symbol(
                name=name,
                kind="class",
                range=self._make_range(line, line),
                file=filepath,
                modifiers=["export"] if m.group(1) else [],
                metadata={"extends": extends, "implements": implements},
            ))

            # Parse methods within class body
            class_start = m.end()
            brace_depth = 1
            i = class_start
            while i < len(source) and brace_depth > 0:
                if source[i] == '{':
                    brace_depth += 1
                elif source[i] == '}':
                    brace_depth -= 1
                i += 1

            class_body = source[class_start:i - 1]
            self._parse_methods_in_body(class_body, name, result, filepath, line)

    def _parse_methods_in_body(self, body: str, class_name: str, result: ParseResult, filepath: str, offset: int) -> None:
        """Parse methods inside a class body."""
        method_pattern = re.compile(r'^\s+(async\s+)?(\w+)\s*\(([^)]*)\)\s*(?::\s*(\S+))?\s*\{', re.MULTILINE)
        for m in method_pattern.finditer(body):
            is_async = bool(m.group(1))
            name = m.group(2)
            if name in ("if", "for", "while", "switch", "catch", "return"):
                continue
            params_str = m.group(3)
            return_type = m.group(4) or ""
            line = offset + body[:m.start()].count('\n')

            params = self._parse_params(params_str)
            modifiers = ["method"]
            if is_async:
                modifiers.append("async")
            if name.startswith("_"):
                modifiers.append("private")
            if name == "constructor":
                modifiers.append("constructor")

            result.symbols.append(Symbol(
                name=name,
                kind="method",
                range=self._make_range(line, line),
                file=filepath,
                parent=class_name,
                parameters=params,
                return_type=return_type,
                modifiers=modifiers,
                signature=f"{'async ' if is_async else ''}{name}({params_str})",
            ))

    def _parse_functions(self, source: str, result: ParseResult, filepath: str, lines: list) -> None:
        for pattern in self.FUNC_PATTERNS[:3]:
            for m in pattern.finditer(source):
                groups = m.groups()
                line = source[:m.start()].count('\n') + 1

                if len(groups) >= 5:
                    is_export = bool(groups[0])
                    is_async = bool(groups[1] or groups[3])
                    name = groups[2]
                    params_str = groups[4] if len(groups) > 4 else ""
                    return_type = groups[5] if len(groups) > 5 else ""

                    if not name:
                        continue

                    params = self._parse_params(params_str)
                    modifiers = []
                    if is_export:
                        modifiers.append("export")
                    if is_async:
                        modifiers.append("async")

                    result.symbols.append(Symbol(
                        name=name,
                        kind="function",
                        range=self._make_range(line, line),
                        file=filepath,
                        parameters=params,
                        return_type=return_type or "",
                        modifiers=modifiers,
                        signature=f"{'async ' if is_async else ''}function {name}({params_str})",
                    ))

    def _parse_variables(self, source: str, result: ParseResult, filepath: str) -> None:
        """Parse top-level const/let/var declarations."""
        pattern = re.compile(r'^(export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?!function|(\s*\())', re.MULTILINE)
        for m in pattern.finditer(source):
            line = source[:m.start()].count('\n') + 1
            is_export = bool(m.group(1))
            name = m.group(2)

            if name[0] == name[0].upper() and name[0].isalpha():
                kind = "constant"
            else:
                kind = "variable"

            result.symbols.append(Symbol(
                name=name,
                kind=kind,
                range=self._make_range(line, line),
                file=filepath,
                modifiers=["export"] if is_export else [],
            ))

    def _parse_calls(self, source: str, result: ParseResult, filepath: str) -> None:
        """Detect function/method calls."""
        call_pattern = re.compile(r'(\w+(?:\.\w+)*)\s*\(')
        for m in call_pattern.finditer(source):
            name = m.group(1)
            line = source[:m.start()].count('\n') + 1
            if name not in ("if", "for", "while", "switch", "catch", "return", "new", "typeof", "import"):
                result.relationships.append(Relationship(
                    source=f"{filepath}:module:{line}",
                    target=name,
                    kind="calls",
                    range=self._make_range(line, line),
                ))

    def _parse_params(self, params_str: str) -> list[dict]:
        """Parse function parameters."""
        if not params_str.strip():
            return []

        params = []
        for param in params_str.split(","):
            param = param.strip()
            if not param:
                continue

            # Handle destructuring, defaults, types
            param = param.split(":")[0].strip()  # Remove type annotation
            param = param.split("=")[0].strip()  # Remove default value

            # Handle destructuring
            if param.startswith("{") or param.startswith("["):
                params.append({"name": param[:20], "kind": "destructured"})
            elif param.startswith("..."):
                params.append({"name": param[3:], "kind": "rest"})
            elif param.startswith("?"):
                params.append({"name": param[1:], "kind": "optional"})
            else:
                params.append({"name": param})

        return params
