"""
Test Generator — auto-generate unit tests, integration tests, property-based tests.
Analyzes code structure and generates meaningful test cases.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..parsers.base import Symbol, ParseResult


@dataclass
class TestCase:
    name: str
    description: str
    code: str
    kind: str  # unit, integration, edge_case, property


@dataclass
class TestSuite:
    file: str
    framework: str
    imports: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    tests: list[TestCase] = field(default_factory=list)


class TestGenerator:
    """Generate tests from code analysis."""

    FRAMEWORKS = {
        "python": {"pytest": "pytest", "unittest": "unittest"},
        "javascript": {"jest": "jest", "vitest": "vitest", "mocha": "mocha"},
        "go": {"go test": "go test"},
        "rust": {"cargo test": "cargo test"},
        "java": {"junit": "junit5"},
    }

    @classmethod
    def generate_for_symbol(cls, symbol: Symbol, framework: str = "pytest") -> TestCase:
        """Generate a test case for a single symbol."""
        if framework == "pytest":
            return cls._generate_pytest(symbol)
        elif framework == "jest":
            return cls._generate_jest(symbol)
        elif framework == "go test":
            return cls._generate_go_test(symbol)
        return TestCase(name=f"test_{symbol.name}", description="", code="", kind="unit")

    @classmethod
    def generate_for_file(cls, parse_result: ParseResult, framework: str = "pytest") -> TestSuite:
        """Generate a test suite for an entire file."""
        suite = TestSuite(
            file=parse_result.file,
            framework=framework,
        )

        if framework == "pytest":
            suite.imports = ["import pytest"]
            # Add imports for the module being tested
            module = Path(parse_result.file).stem
            suite.imports.append(f"from {module} import " + ", ".join(
                s.name for s in parse_result.functions[:5]))

            for sym in parse_result.functions:
                if not sym.name.startswith("_"):
                    suite.tests.append(cls._generate_pytest(sym))

            for sym in parse_result.classes:
                if not sym.name.startswith("_"):
                    suite.tests.append(cls._generate_pytest_class(sym, parse_result))

        elif framework == "jest":
            module = Path(parse_result.file).stem
            suite.imports = [f"const {{ {', '.join(s.name for s in parse_result.functions[:5])} }} = require('./{module}')"]
            for sym in parse_result.functions:
                suite.tests.append(cls._generate_jest(sym))

        return suite

    @classmethod
    def _generate_pytest(cls, symbol: Symbol) -> TestCase:
        """Generate a pytest test case."""
        params = symbol.parameters
        test_name = f"test_{symbol.name}"

        # Build test code
        lines = [f"def {test_name}():"]
        lines.append(f'    """Test {symbol.name}."""')

        if not params:
            # No params — just call it
            lines.append(f"    result = {symbol.name}()")
            lines.append(f"    assert result is not None")
        else:
            # Generate test with mock params
            args = []
            for p in params:
                pname = p.get("name", "arg")
                ptype = p.get("type", "str")
                if ptype in ("str", "string"):
                    args.append(f'{pname}="test"')
                elif ptype in ("int", "integer"):
                    args.append(f"{pname}=1")
                elif ptype in ("float", "number"):
                    args.append(f"{pname}=1.0")
                elif ptype in ("bool", "boolean"):
                    args.append(f"{pname}=True")
                elif ptype in ("list", "List", "array"):
                    args.append(f"{pname}=[]")
                elif ptype in ("dict", "Dict", "object", "map"):
                    args.append(f"{pname}={{}}")
                else:
                    args.append(f"{pname}=None")

            lines.append(f"    result = {symbol.name}({', '.join(args)})")
            lines.append(f"    assert result is not None")

        # Edge cases
        lines.append("")
        lines.append(f"def {test_name}_edge_cases():")
        lines.append(f'    """Test {symbol.name} with edge cases."""')
        if any(p.get("type") in ("str", "string") for p in params):
            lines.append(f"    # Empty string")
            lines.append(f"    with pytest.raises(Exception):")
            lines.append(f"        {symbol.name}('')")
        if any(p.get("type") in ("int", "integer", "float") for p in params):
            lines.append(f"    # Negative values")
            lines.append(f"    with pytest.raises(Exception):")
            lines.append(f"        {symbol.name}(-1)")

        code = "\n".join(lines)

        return TestCase(
            name=test_name,
            description=f"Test {symbol.name} with valid and edge case inputs",
            code=code,
            kind="unit",
        )

    @classmethod
    def _generate_pytest_class(cls, symbol: Symbol, parse_result: ParseResult) -> TestCase:
        """Generate pytest test cases for a class."""
        methods = [s for s in parse_result.methods if s.parent == symbol.name]

        lines = [f"class Test{symbol.name}:"]
        lines.append(f'    """Tests for {symbol.name}."""')
        lines.append("")
        lines.append("    def setup_method(self):")
        lines.append(f"        self.instance = {symbol.name}()")
        lines.append("")

        for method in methods:
            if method.name.startswith("_"):
                continue
            lines.append(f"    def test_{method.name}(self):")
            lines.append(f'        """Test {method.name}."""')
            if method.parameters:
                args = [f"{p.get('name', 'arg')}=None" for p in method.parameters]
                lines.append(f"        result = self.instance.{method.name}({', '.join(args)})")
            else:
                lines.append(f"        result = self.instance.{method.name}()")
            lines.append(f"        assert result is not None")
            lines.append("")

        return TestCase(
            name=f"test_{symbol.name}",
            description=f"Test class {symbol.name}",
            code="\n".join(lines),
            kind="unit",
        )

    @classmethod
    def _generate_jest(cls, symbol: Symbol) -> TestCase:
        """Generate a Jest test case."""
        params = symbol.parameters
        lines = [f"describe('{symbol.name}', () => {{"]
        lines.append(f"  it('should work with valid input', () => {{")
        if params:
            args = [f"'test'" if p.get("type") in ("str",) else "1" for p in params]
            lines.append(f"    const result = {symbol.name}({', '.join(args)})")
        else:
            lines.append(f"    const result = {symbol.name}()")
        lines.append(f"    expect(result).toBeDefined()")
        lines.append(f"  }})")
        lines.append(f"  it('should throw on invalid input', () => {{")
        lines.append(f"    expect(() => {symbol.name}(null)).toThrow()")
        lines.append(f"  }})")
        lines.append(f"}})")

        return TestCase(
            name=f"test_{symbol.name}",
            description=f"Test {symbol.name}",
            code="\n".join(lines),
            kind="unit",
        )

    @classmethod
    def _generate_go_test(cls, symbol: Symbol) -> TestCase:
        """Generate a Go test case."""
        lines = [f"func Test{symbol.name.title()}(t *testing.T) {{", ""]

        if symbol.parameters:
            args = []
            for p in symbol.parameters:
                ptype = p.get("type", "string")
                if ptype == "string":
                    args.append('"test"')
                elif ptype in ("int", "int64", "int32"):
                    args.append("1")
                elif ptype in ("float64", "float32"):
                    args.append("1.0")
                elif ptype == "bool":
                    args.append("true")
                else:
                    args.append(f"{ptype}{{}}")
            lines.append(f"    result := {symbol.name}({', '.join(args)})")
        else:
            lines.append(f"    result := {symbol.name}()")

        lines.append("    if result == nil {")
        lines.append('        t.Error("expected non-nil result")')
        lines.append("    }")
        lines.append("}")

        return TestCase(
            name=f"Test{symbol.name.title()}",
            description=f"Test {symbol.name}",
            code="\n".join(lines),
            kind="unit",
        )

    @classmethod
    def render_suite(cls, suite: TestSuite) -> str:
        """Render a test suite to a string."""
        lines = []
        for imp in suite.imports:
            lines.append(imp)
        lines.append("")
        lines.append("")
        for fixture in suite.fixtures:
            lines.append(fixture)
            lines.append("")
        for test in suite.tests:
            lines.append(test.code)
            lines.append("")
        return "\n".join(lines)
