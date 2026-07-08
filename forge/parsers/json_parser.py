"""JSON Parser — structural parsing for JSON files."""
from __future__ import annotations
import json
from .base import BaseParser, ParseResult, Symbol, Range

class JsonParser(BaseParser):
    """JSON parser."""
    def parse(self, source: str, filepath: str = "<string>") -> ParseResult:
        result = ParseResult(file=filepath, language="json")
        try:
            data = json.loads(source)
            self._extract_keys(data, result, filepath, "")
        except json.JSONDecodeError as e:
            result.errors.append(f"JSON parse error: {e}")
        return result

    def _extract_keys(self, data, result, filepath, prefix):
        if isinstance(data, dict):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                result.symbols.append(Symbol(name=full_key, kind="key", range=self._make_range(1, 1), file=filepath))
                if isinstance(value, (dict, list)):
                    self._extract_keys(value, result, filepath, full_key)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    self._extract_keys(item, result, filepath, f"{prefix}[{i}]")
