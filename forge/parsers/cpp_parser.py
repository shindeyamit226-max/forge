"""C++ Parser — extends C parser with classes, templates, namespaces, etc."""
from __future__ import annotations
import re
from .c_parser import CParser
from .base import ParseResult, Symbol, Import, Range

class CppParser(CParser):
    """C++ language parser."""
    CLASS_PATTERN = re.compile(r'^(?:class|struct)\s+(\w+)(?:\s*:\s*(?:public|private|protected)\s+(\w+))?\s*\{', re.MULTILINE)
    NAMESPACE_PATTERN = re.compile(r'^namespace\s+(\w+)\s*\{', re.MULTILINE)
    TEMPLATE_PATTERN = re.compile(r'^template\s*<([^>]+)>\s*(class|struct|void|int|auto)\s+(\w+)', re.MULTILINE)
    USING_PATTERN = re.compile(r'^using\s+(\w+)\s*=', re.MULTILINE)
    OPERATOR_PATTERN = re.compile(r'operator\s*([+\-*/=<>!&|^~\[\]()]+)\s*\(', re.MULTILINE)
    FRIEND_PATTERN = re.compile(r'friend\s+(?:class\s+)?(\w+)', re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="cpp")
        # Use C parser for base
        c_result = super().parse(source, filepath)
        result.symbols.extend(c_result.symbols)
        result.imports.extend(c_result.imports)
        # Namespaces
        for m in self.NAMESPACE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="namespace", range=self._make_range(line, line), file=filepath))
        # Classes
        for m in self.CLASS_PATTERN.finditer(source):
            name, base = m.group(1), m.group(2) or ""
            line = source[:m.start()].count('\n') + 1
            body = self._extract_block(source, m.end())
            result.symbols.append(Symbol(name=name, kind="class", range=self._make_range(line, line + body.count('\n')),
                file=filepath, metadata={"base": base}))
            # Parse methods
            for mm in re.finditer(r'(?:(?:virtual|static|const|override)\s+)*(\w+(?:\s*\*)?)\s+(\w+)\s*\(([^)]*)\)', body):
                mline = line + body[:mm.start()].count('\n')
                result.symbols.append(Symbol(name=mm.group(2), kind="method", range=self._make_range(mline, mline),
                    file=filepath, parent=name, return_type=mm.group(1)))
        # Templates
        for m in self.TEMPLATE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(3), kind="template", range=self._make_range(line, line),
                file=filepath, metadata={"template_params": m.group(1)}))
        # Using aliases
        for m in self.USING_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="type", range=self._make_range(line, line), file=filepath))
        return result
