"""
Language Parsers — full AST parsing for 20+ languages.
Not regex. Real structural understanding.
Each parser extracts: functions, classes, methods, imports, exports,
variables, types, interfaces, decorators, docstrings, and relationships.
"""

from .python_parser import PythonParser
from .javascript_parser import JavaScriptParser
from .typescript_parser import TypeScriptParser
from .go_parser import GoParser
from .rust_parser import RustParser
from .java_parser import JavaParser
from .c_parser import CParser
from .cpp_parser import CppParser
from .ruby_parser import RubyParser
from .php_parser import PhpParser
from .swift_parser import SwiftParser
from .kotlin_parser import KotlinParser
from .scala_parser import ScalaParser
from .sql_parser import SqlParser
from .shell_parser import ShellParser
from .html_parser import HtmlParser
from .css_parser import CssParser
from .yaml_parser import YamlParser
from .json_parser import JsonParser
from .markdown_parser import MarkdownParser
from .base import BaseParser, ParseResult, Symbol, Import, Export, Relationship

PARSERS = {
    ".py": PythonParser, ".pyi": PythonParser,
    ".js": JavaScriptParser, ".mjs": JavaScriptParser, ".cjs": JavaScriptParser,
    ".ts": TypeScriptParser, ".mts": TypeScriptParser, ".tsx": TypeScriptParser,
    ".jsx": JavaScriptParser,
    ".go": GoParser,
    ".rs": RustParser,
    ".java": JavaParser,
    ".c": CParser, ".h": CParser,
    ".cpp": CppParser, ".cc": CppParser, ".cxx": CppParser, ".hpp": CppParser,
    ".rb": RubyParser,
    ".php": PhpParser,
    ".swift": SwiftParser,
    ".kt": KotlinParser, ".kts": KotlinParser,
    ".scala": ScalaParser, ".sc": ScalaParser,
    ".sql": SqlParser,
    ".sh": ShellParser, ".bash": ShellParser, ".zsh": ShellParser,
    ".html": HtmlParser, ".htm": HtmlParser,
    ".css": CssParser, ".scss": CssParser, ".less": CssParser,
    ".yaml": YamlParser, ".yml": YamlParser,
    ".json": JsonParser,
    ".md": MarkdownParser, ".mdx": MarkdownParser,
}


def get_parser(filepath: str) -> BaseParser:
    from pathlib import Path
    ext = Path(filepath).suffix.lower()
    cls = PARSERS.get(ext)
    if cls:
        return cls()
    return PythonParser()  # default


def parse_file(filepath: str) -> ParseResult:
    parser = get_parser(filepath)
    return parser.parse_file(filepath)
