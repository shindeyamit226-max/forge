"""SQL Parser — structural parsing for SQL files."""
from __future__ import annotations
import re
from .base import BaseParser, ParseResult, Symbol, Range

class SqlParser(BaseParser):
    """SQL parser for DDL and DML."""
    TABLE_PATTERN = re.compile(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', re.IGNORECASE | re.MULTILINE)
    VIEW_PATTERN = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    INDEX_PATTERN = re.compile(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    PROCEDURE_PATTERN = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    FUNCTION_PATTERN = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    TRIGGER_PATTERN = re.compile(r'CREATE\s+TRIGGER\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    INSERT_PATTERN = re.compile(r'INSERT\s+INTO\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    SELECT_PATTERN = re.compile(r'SELECT\s+.+?\s+FROM\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    ALTER_PATTERN = re.compile(r'ALTER\s+TABLE\s+(\w+)', re.IGNORECASE | re.MULTILINE)
    DROP_PATTERN = re.compile(r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)', re.IGNORECASE | re.MULTILINE)

    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="sql")
        for m in self.TABLE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="table", range=self._make_range(line, line), file=filepath))
        for m in self.VIEW_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="view", range=self._make_range(line, line), file=filepath))
        for m in self.INDEX_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="index", range=self._make_range(line, line), file=filepath))
        for m in self.PROCEDURE_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="procedure", range=self._make_range(line, line), file=filepath))
        for m in self.FUNCTION_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="function", range=self._make_range(line, line), file=filepath))
        for m in self.TRIGGER_PATTERN.finditer(source):
            line = source[:m.start()].count('\n') + 1
            result.symbols.append(Symbol(name=m.group(1), kind="trigger", range=self._make_range(line, line), file=filepath))
        return result
