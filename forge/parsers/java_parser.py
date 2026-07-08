"""Java Parser — structural parsing for Java source files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Import, Export, Relationship, Range, Position

class JavaParser(BaseParser):
    """Java language parser."""
    CLASS_PATTERN = re.compile(r'^(public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:<[^>]*>)?\s*(?:extends\s+(\w+))?\s*(?:implements\s+([^{]+))?\s*\{', re.MULTILINE)
    INTERFACE_PATTERN = re.compile(r'^(public\s+)?interface\s+(\w+)(?:<[^>]*>)?\s*(?:extends\s+([^{]+))?\s*\{', re.MULTILINE)
    ENUM_PATTERN = re.compile(r'^(public\s+)?enum\s+(\w+)\s*\{', re.MULTILINE)
    ANNOTATION_PATTERN = re.compile(r'^@interface\s+(\w+)', re.MULTILINE)
    METHOD_PATTERN = re.compile(r'^\s+(public|private|protected)?\s*(static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:abstract\s+)?(?:<[^>]*>\s+)?(\w+(?:<[^>]*>)?(?:\[\])?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[^{]*)?\{', re.MULTILINE)
    FIELD_PATTERN = re.compile(r'^\s+(public|private|protected)?\s*(static\s+)?(?:final\s+)?(\w+(?:<[^>]*>)?(?:\[\])?)\s+(\w+)\s*[;=]', re.MULTILINE)
    IMPORT_PATTERN = re.compile(r'^import\s+(static\s+)?([\w.]+(?:\.\*)?)\s*;', re.MULTILINE)
    CONSTRUCTOR_PATTERN = re.compile(r'^\s+(public|private|protected)?\s*(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[^{]*)?\{', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="java")

        # Imports
        for m in self.IMPORT_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            is_static = bool(m.group(1))
            module = m.group(2)
            names = [module.split('.')[-1]] if not module.endswith('.*') else ['*']
            result.imports.append(Import(module=module, names=names, is_wildcard=module.endswith('.*'),
                range=self._make_range(line, line), kind="static_import" if is_static else "import"))

        # Annotations
        for m in self.ANNOTATION_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="annotation", range=self._make_range(line, line), file=filepath))

        # Interfaces
        for m in self.INTERFACE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            extends = [e.strip() for e in m.group(3).split(',')] if m.group(3) else []
            result.symbols.append(Symbol(name=m.group(2), kind="interface", range=self._make_range(line, line),
                file=filepath, modifiers=["public"] if m.group(1) else [], metadata={"extends": extends}))

        # Enums
        for m in self.ENUM_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(2), kind="enum", range=self._make_range(line, line),
                file=filepath, modifiers=["public"] if m.group(1) else []))

        # Classes
        for m in self.CLASS_PATTERN.finditer(source):
            name = m.group(2)
            extends = m.group(3) or ""
            implements = [i.strip() for i in m.group(4).split(',')] if m.group(4) else []
            line = source[:m.start()].count('\n') + 1
            body_start = m.end()
            body = self._extract_block(source, body_start)

            result.symbols.append(Symbol(name=name, kind="class", range=self._make_range(line, line + body.count('\n')),
                file=filepath, modifiers=["public"] if m.group(1) else [],
                metadata={"extends": extends, "implements": implements}))

            # Parse methods within class
            for fm in self.METHOD_PATTERN.finditer(body):
                mline = line + body[:fm.start()].count('\n')
                access = fm.group(1) or "package"
                is_static = bool(fm.group(2))
                return_type = fm.group(3)
                method_name = fm.group(4)
                params = fm.group(5)
                modifiers = [access]
                if is_static: modifiers.append("static")
                result.symbols.append(Symbol(name=method_name, kind="method", range=self._make_range(mline, mline),
                    file=filepath, parent=name, return_type=return_type, modifiers=modifiers,
                    parameters=self._parse_java_params(params)))

            # Constructors
            for cm in self.CONSTRUCTOR_PATTERN.finditer(body):
                if cm.group(2) == name:
                    cline = line + body[:cm.start()].count('\n')
                    result.symbols.append(Symbol(name=name, kind="constructor", range=self._make_range(cline, cline),
                        file=filepath, parent=name, modifiers=[cm.group(1) or "package"],
                        parameters=self._parse_java_params(cm.group(3))))

            # Fields
            for ff in self.FIELD_PATTERN.finditer(body):
                fline = line + body[:ff.start()].count('\n')
                result.symbols.append(Symbol(name=ff.group(4), kind="field", range=self._make_range(fline, fline),
                    file=filepath, parent=name, return_type=ff.group(3),
                    modifiers=[ff.group(1) or "package"] + (["static"] if ff.group(2) else [])))

        return result

    def _extract_block(self, source: str, start: int) -> str:
        depth, i = 1, start
        while i < len(source) and depth > 0:
            if source[i] == '{': depth += 1
            elif source[i] == '}': depth -= 1
            i += 1
        return source[start:i-1]

    def _parse_java_params(self, params_str: str) -> list[dict]:
        if not params_str.strip(): return []
        params = []
        for p in params_str.split(','):
            p = p.strip()
            if not p: continue
            parts = p.split()
            if len(parts) >= 2:
                params.append({"name": parts[-1], "type": ' '.join(parts[:-1])})
        return params
