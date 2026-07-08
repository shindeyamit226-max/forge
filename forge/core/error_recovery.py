"""
Error Recovery Engine — parse compiler/test/lint errors, auto-fix.
Understands errors from Python, JavaScript, TypeScript, Go, Rust, Java.
The key differentiator: Forge doesn't just show errors, it FIXES them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ParsedError:
    """A structured error parsed from compiler/test/lint output."""
    file: str
    line: int
    column: int
    severity: str  # error, warning, info
    message: str
    code: Optional[str] = None  # Error code (e.g., E501, TS2322)
    source: str = ""  # Compiler, pytest, eslint, etc.
    context: str = ""  # Surrounding code context
    suggestion: str = ""  # Suggested fix
    raw: str = ""  # Raw error text

    @property
    def location(self) -> str:
        if self.column:
            return f"{self.file}:{self.line}:{self.column}"
        return f"{self.file}:{self.line}"


@dataclass
class ErrorAnalysis:
    """Analysis of a set of errors."""
    errors: list[ParsedError] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)  # Common patterns detected
    root_cause: str = ""
    fix_strategy: str = ""
    affected_files: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "warning")

    def summary(self) -> str:
        lines = [f"Found {self.error_count} errors in {len(self.affected_files)} files"]
        for e in self.errors[:10]:
            lines.append(f"  {e.severity}: {e.location}: {e.message[:100]}")
        if self.root_cause:
            lines.append(f"\nRoot cause: {self.root_cause}")
        if self.fix_strategy:
            lines.append(f"Fix strategy: {self.fix_strategy}")
        return "\n".join(lines)


class ErrorParser:
    """Base class for error parsers."""

    def parse(self, output: str) -> list[ParsedError]:
        raise NotImplementedError


class PythonErrorParser(ErrorParser):
    """Parse Python errors from tracebacks, pytest, mypy, ruff, flake8."""

    # Python traceback
    TRACEBACK_PATTERN = re.compile(
        r'File "([^"]+)", line (\d+)\s*\n\s*(.+)',
    )
    TRACEBACK_ERROR = re.compile(
        r'^(\w+(?:\.\w+)*(?:Error|Exception|Warning)):\s*(.+)',
        re.MULTILINE,
    )

    # pytest
    PYTEST_PATTERN = re.compile(
        r'^(.+?):(\d+):\s+(AssertionError|TypeError|ValueError|KeyError|AttributeError|NameError|ImportError|SyntaxError|IndexError|RuntimeError|Exception)',
        re.MULTILINE,
    )
    PYTEST_FAIL = re.compile(
        r'^FAIL:\s+(.+)',
        re.MULTILINE,
    )

    # mypy
    MYPY_PATTERN = re.compile(
        r'^(.+?):(\d+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[(.+?)\])?$',
        re.MULTILINE,
    )

    # ruff/flake8
    LINT_PATTERN = re.compile(
        r'^(.+?):(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)',
        re.MULTILINE,
    )

    def parse(self, output: str) -> list[ParsedError]:
        errors = []

        # Try mypy first (most structured)
        for m in self.MYPY_PATTERN.finditer(output):
            errors.append(ParsedError(
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity=m.group(4),
                message=m.group(5),
                code=m.group(6),
                source="mypy",
                raw=m.group(0),
            ))

        # Try ruff/flake8
        for m in self.LINT_PATTERN.finditer(output):
            errors.append(ParsedError(
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity="error" if m.group(4).startswith("E") else "warning",
                message=m.group(5),
                code=m.group(4),
                source="linter",
                raw=m.group(0),
            ))

        # Try pytest errors
        for m in self.PYTEST_PATTERN.finditer(output):
            errors.append(ParsedError(
                file=m.group(1),
                line=int(m.group(2)),
                column=0,
                severity="error",
                message=m.group(3),
                source="pytest",
                raw=m.group(0),
            ))

        # Try traceback
        for m in self.TRACEBACK_ERROR.finditer(output):
            errors.append(ParsedError(
                file="<traceback>",
                line=0,
                column=0,
                severity="error",
                message=m.group(2),
                code=m.group(1),
                source="python",
                raw=m.group(0),
            ))

        return errors


class JavaScriptErrorParser(ErrorParser):
    """Parse JavaScript/TypeScript errors."""

    # TypeScript
    TS_PATTERN = re.compile(
        r'^(.+?)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)',
        re.MULTILINE,
    )

    # ESLint
    ESLINT_PATTERN = re.compile(
        r'^\s+(\d+):(\d+)\s+(error|warning)\s+(.+?)(?:\s+([a-z-]+))?$',
        re.MULTILINE,
    )

    # Node.js
    NODE_ERROR = re.compile(
        r'^(?:SyntaxError|TypeError|ReferenceError|RangeError|Error):\s*(.+)',
        re.MULTILINE,
    )
    NODE_AT = re.compile(
        r'^\s+at\s+.+\((.+):(\d+):\d+\)',
        re.MULTILINE,
    )

    # Vite/Webpack
    VITE_ERROR = re.compile(
        r'^(.+?):(\d+):(\d+):\s+(error):\s+(.+)',
        re.MULTILINE,
    )

    def parse(self, output: str) -> list[ParsedError]:
        errors = []

        # TypeScript
        for m in self.TS_PATTERN.finditer(output):
            errors.append(ParsedError(
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity=m.group(4),
                message=m.group(6),
                code=m.group(5),
                source="tsc",
                raw=m.group(0),
            ))

        # Vite/esbuild
        for m in self.VITE_ERROR.finditer(output):
            errors.append(ParsedError(
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity=m.group(4),
                message=m.group(5),
                source="vite",
                raw=m.group(0),
            ))

        # Node.js errors
        for m in self.NODE_ERROR.finditer(output):
            errors.append(ParsedError(
                file="node",
                line=0,
                column=0,
                severity="error",
                message=m.group(1),
                source="node",
                raw=m.group(0),
            ))

        return errors


class GoErrorParser(ErrorParser):
    """Parse Go compiler errors."""

    GO_PATTERN = re.compile(
        r'^(.+?):(\d+):(\d+):\s+(.+)',
        re.MULTILINE,
    )

    def parse(self, output: str) -> list[ParsedError]:
        errors = []
        for m in self.GO_PATTERN.finditer(output):
            msg = m.group(4)
            severity = "error" if "undefined" in msg or "cannot" in msg else "warning"
            errors.append(ParsedError(
                file=m.group(1),
                line=int(m.group(2)),
                column=int(m.group(3)),
                severity=severity,
                message=msg,
                source="go",
                raw=m.group(0),
            ))
        return errors


class RustErrorParser(ErrorParser):
    """Parse Rust compiler errors."""

    RUST_PATTERN = re.compile(
        r'^error\[?(E\d+)?\]?:\s+(.+)\s*\n\s*-->\s+(.+):(\d+):(\d+)',
        re.MULTILINE,
    )
    RUST_SIMPLE = re.compile(
        r'^error:\s+(.+)\s*\n\s*-->\s+(.+):(\d+):(\d+)',
        re.MULTILINE,
    )

    def parse(self, output: str) -> list[ParsedError]:
        errors = []
        for m in self.RUST_PATTERN.finditer(output):
            errors.append(ParsedError(
                file=m.group(3),
                line=int(m.group(4)),
                column=int(m.group(5)),
                severity="error",
                message=m.group(2),
                code=m.group(1),
                source="rustc",
                raw=m.group(0),
            ))
        for m in self.RUST_SIMPLE.finditer(output):
            errors.append(ParsedError(
                file=m.group(2),
                line=int(m.group(3)),
                column=int(m.group(4)),
                severity="error",
                message=m.group(1),
                source="rustc",
                raw=m.group(0),
            ))
        return errors


class TestErrorParser(ErrorParser):
    """Parse test runner output (pytest, jest, go test)."""

    # pytest
    PYTEST_FAIL = re.compile(
        r'^(FAIL|ERROR|FAILED)\s+(.+)',
        re.MULTILINE,
    )
    PYTEST_ASSERT = re.compile(
        r'^E\s+(.+)',
        re.MULTILINE,
    )

    # jest
    JEST_FAIL = re.compile(
        r'●\s+(.+)',
        re.MULTILINE,
    )

    def parse(self, output: str) -> list[ParsedError]:
        errors = []

        for m in self.PYTEST_FAIL.finditer(output):
            errors.append(ParsedError(
                file=m.group(2).strip(),
                line=0,
                column=0,
                severity="error",
                message=f"Test {m.group(1)}: {m.group(2)}",
                source="pytest",
                raw=m.group(0),
            ))

        for m in self.JEST_FAIL.finditer(output):
            errors.append(ParsedError(
                file="test",
                line=0,
                column=0,
                severity="error",
                message=m.group(1),
                source="jest",
                raw=m.group(0),
            ))

        return errors


# Registry of parsers
_PARSERS = {
    "python": PythonErrorParser(),
    "javascript": JavaScriptErrorParser(),
    "typescript": JavaScriptErrorParser(),
    "go": GoErrorParser(),
    "rust": RustErrorParser(),
    "test": TestErrorParser(),
}


class ErrorRecoveryEngine:
    """
    Analyzes errors and generates fix strategies.
    This is what makes Forge self-correcting.
    """

    def __init__(self):
        self.parsers = _PARSERS
        self._error_history: list[ErrorAnalysis] = []

    def parse_errors(self, output: str, language: str = "auto") -> list[ParsedError]:
        """Parse error output into structured errors."""
        if language == "auto":
            language = self._detect_language(output)

        parser = self.parsers.get(language)
        if not parser:
            # Try all parsers
            all_errors = []
            for p in self.parsers.values():
                all_errors.extend(p.parse(output))
            return all_errors

        return parser.parse(output)

    def analyze(self, output: str, language: str = "auto") -> ErrorAnalysis:
        """Parse and analyze errors, generating a fix strategy."""
        errors = self.parse_errors(output, language)

        if not errors:
            return ErrorAnalysis()

        analysis = ErrorAnalysis(errors=errors)
        analysis.affected_files = list(set(e.file for e in errors if e.file != "<traceback>"))

        # Detect patterns
        analysis.patterns = self._detect_patterns(errors)
        analysis.root_cause = self._identify_root_cause(errors)
        analysis.fix_strategy = self._suggest_fix_strategy(errors, analysis)

        self._error_history.append(analysis)
        return analysis

    def _detect_language(self, output: str) -> str:
        """Auto-detect language from error output."""
        if "Traceback" in output or "pytest" in output:
            return "python"
        if "TS" in output and "error TS" in output:
            return "typescript"
        if ".js:" in output or ".jsx:" in output:
            return "javascript"
        if "cannot use" in output or "undefined:" in output:
            return "go"
        if "error[E" in output or "-->" in output and "rustc" in output:
            return "rust"
        return "python"  # Default

    def _detect_patterns(self, errors: list[ParsedError]) -> list[str]:
        """Detect common error patterns."""
        patterns = []

        # Type errors cluster
        type_errors = [e for e in errors if "type" in e.message.lower() or e.code in ("TS2322", "TS2345")]
        if len(type_errors) > 2:
            patterns.append("Multiple type errors — possible interface change or migration issue")

        # Import errors
        import_errors = [e for e in errors if "import" in e.message.lower() or "module" in e.message.lower()]
        if import_errors:
            patterns.append("Import/module errors — possible missing dependency or path change")

        # Undefined/not found
        undef_errors = [e for e in errors if "undefined" in e.message.lower() or "not found" in e.message.lower() or "cannot find" in e.message.lower()]
        if undef_errors:
            patterns.append("Undefined references — possible deleted symbols or typos")

        # Syntax errors
        syntax_errors = [e for e in errors if "syntax" in e.message.lower() or "unexpected" in e.message.lower()]
        if syntax_errors:
            patterns.append("Syntax errors — check recent edits for typos or missing brackets")

        # Test failures
        test_errors = [e for e in errors if e.source in ("pytest", "jest")]
        if test_errors:
            patterns.append(f"Test failures ({len(test_errors)}) — behavior changed or regression")

        return patterns

    def _identify_root_cause(self, errors: list[ParsedError]) -> str:
        """Identify the most likely root cause."""
        if not errors:
            return ""

        # Single file = likely local issue
        files = set(e.file for e in errors if e.file != "<traceback>")
        if len(files) == 1:
            return f"All errors in {files.pop()} — likely a recent edit introduced issues"

        # Many files with same error type = systemic
        sources = Counter(e.source for e in errors)
        if len(sources) == 1:
            source = list(sources.keys())[0]
            return f"All errors from {source} — possible configuration or dependency issue"

        # Import chain
        import_errors = [e for e in errors if "import" in e.message.lower()]
        if import_errors:
            return "Import chain error — fixing the root import may cascade-fix others"

        return "Multiple sources — prioritize fixing the first error, others may resolve"

    def _suggest_fix_strategy(
        self, errors: list[ParsedError], analysis: ErrorAnalysis,
    ) -> str:
        """Suggest a fix strategy based on error analysis."""
        strategies = []

        if "Import" in analysis.root_cause or "import" in str(analysis.patterns):
            strategies.append("1. Check if dependencies are installed (pip install / npm install)")
            strategies.append("2. Verify import paths are correct")
            strategies.append("3. Check for circular imports")

        if "Syntax" in str(analysis.patterns):
            strategies.append("1. Review the most recently edited file for syntax errors")
            strategies.append("2. Check for unclosed brackets, quotes, or missing colons")

        if "type" in str(analysis.patterns).lower():
            strategies.append("1. Check type annotations match actual usage")
            strategies.append("2. Verify function signatures haven't changed")
            strategies.append("3. Look for recent interface/type changes")

        if "Test" in str(analysis.patterns):
            strategies.append("1. Run the specific failing test in isolation")
            strategies.append("2. Check if the test expectations match current behavior")
            strategies.append("3. Review recent code changes that affect the tested path")

        if not strategies:
            strategies.append("1. Fix the first error first — others may cascade")
            strategies.append("2. Read the error message carefully for hints")
            strategies.append("3. Check the file and line number referenced")

        return "\n".join(strategies)

    def generate_fix_prompt(self, analysis: ErrorAnalysis) -> str:
        """Generate a prompt for the LLM to fix the errors."""
        prompt_parts = [
            "The following errors occurred. Analyze them and fix the root cause.",
            "",
            "Errors:",
        ]

        for e in analysis.errors[:10]:
            prompt_parts.append(f"  {e.location}: [{e.severity}] {e.message}")
            if e.context:
                prompt_parts.append(f"    Context: {e.context[:200]}")

        if analysis.patterns:
            prompt_parts.append(f"\nDetected patterns: {'; '.join(analysis.patterns)}")
        if analysis.root_cause:
            prompt_parts.append(f"Root cause: {analysis.root_cause}")
        if analysis.fix_strategy:
            prompt_parts.append(f"\nSuggested fix strategy:\n{analysis.fix_strategy}")

        prompt_parts.append("\nFix the root cause of these errors. Don't just fix symptoms.")

        return "\n".join(prompt_parts)

    @property
    def history(self) -> list[ErrorAnalysis]:
        return self._error_history

    def clear_history(self) -> None:
        self._error_history.clear()


# Import Counter at module level
from collections import Counter
