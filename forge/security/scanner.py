"""
Security Scanner — detect vulnerabilities and anti-patterns in code.
This is what makes Forge useful for security-conscious teams.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SecurityIssue:
    """A detected security issue."""
    rule: str
    severity: str  # critical, high, medium, low, info
    message: str
    file: str
    line: int
    column: int = 0
    code_snippet: str = ""
    cwe: str = ""  # CWE ID
    fix_suggestion: str = ""


@dataclass
class ScanResult:
    """Security scan results."""
    issues: list[SecurityIssue] = field(default_factory=list)
    files_scanned: int = 0
    scan_time_ms: float = 0.0

    @property
    def critical(self) -> list[SecurityIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def high(self) -> list[SecurityIssue]:
        return [i for i in self.issues if i.severity == "high"]

    @property
    def medium(self) -> list[SecurityIssue]:
        return [i for i in self.issues if i.severity == "medium"]

    def summary(self) -> str:
        lines = [f"Security Scan: {len(self.issues)} issues found"]
        lines.append(f"  Critical: {len(self.critical)}")
        lines.append(f"  High: {len(self.high)}")
        lines.append(f"  Medium: {len(self.medium)}")
        lines.append(f"  Low/Info: {len(self.issues) - len(self.critical) - len(self.high) - len(self.medium)}")
        lines.append("")
        for issue in sorted(self.issues, key=lambda i: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(i.severity, 5)):
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(issue.severity, "⚪")
            lines.append(f"  {icon} [{issue.severity}] {issue.file}:{issue.line}")
            lines.append(f"     {issue.message}")
            if issue.fix_suggestion:
                lines.append(f"     Fix: {issue.fix_suggestion}")
            lines.append("")
        return "\n".join(lines)


# Security rules
RULES = [
    # Hardcoded secrets
    {
        "id": "hardcoded-secret",
        "pattern": re.compile(r'(?:password|secret|api_key|apikey|token|private_key)\s*=\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
        "severity": "critical",
        "message": "Hardcoded secret detected",
        "cwe": "CWE-798",
        "fix": "Use environment variables or a secrets manager",
    },
    # SQL Injection
    {
        "id": "sql-injection",
        "pattern": re.compile(r'(?:execute|cursor\.execute|query)\s*\(\s*[f"\'].*\{', re.IGNORECASE),
        "severity": "critical",
        "message": "Potential SQL injection via string formatting",
        "cwe": "CWE-89",
        "fix": "Use parameterized queries instead of string formatting",
    },
    {
        "id": "sql-injection-concat",
        "pattern": re.compile(r'(?:execute|query)\s*\(\s*["\'].*["\']\s*\+', re.IGNORECASE),
        "severity": "critical",
        "message": "Potential SQL injection via string concatenation",
        "cwe": "CWE-89",
        "fix": "Use parameterized queries",
    },
    # XSS
    {
        "id": "xss-innerhtml",
        "pattern": re.compile(r'\.innerHTML\s*=', re.IGNORECASE),
        "severity": "high",
        "message": "Potential XSS via innerHTML assignment",
        "cwe": "CWE-79",
        "fix": "Use textContent or a sanitization library",
    },
    {
        "id": "xss-dangerouslySetInnerHTML",
        "pattern": re.compile(r'dangerouslySetInnerHTML', re.IGNORECASE),
        "severity": "high",
        "message": "Potential XSS via dangerouslySetInnerHTML",
        "cwe": "CWE-79",
        "fix": "Sanitize HTML content before rendering",
    },
    # Insecure crypto
    {
        "id": "weak-crypto",
        "pattern": re.compile(r'\b(?:md5|sha1)\s*\(', re.IGNORECASE),
        "severity": "medium",
        "message": "Weak cryptographic hash function",
        "cwe": "CWE-328",
        "fix": "Use SHA-256 or stronger hash functions",
    },
    # Eval / exec
    {
        "id": "eval-usage",
        "pattern": re.compile(r'\beval\s*\(', re.IGNORECASE),
        "severity": "high",
        "message": "Use of eval() — potential code injection",
        "cwe": "CWE-95",
        "fix": "Avoid eval() — use safe alternatives",
    },
    {
        "id": "exec-usage",
        "pattern": re.compile(r'\bexec\s*\(', re.IGNORECASE),
        "severity": "high",
        "message": "Use of exec() — potential code injection",
        "cwe": "CWE-95",
        "fix": "Avoid exec() — use safe alternatives",
    },
    # Insecure deserialization
    {
        "id": "pickle-usage",
        "pattern": re.compile(r'\bpickle\.loads?\s*\(', re.IGNORECASE),
        "severity": "high",
        "message": "Insecure deserialization with pickle",
        "cwe": "CWE-502",
        "fix": "Use JSON or other safe serialization formats",
    },
    # Path traversal
    {
        "id": "path-traversal",
        "pattern": re.compile(r'open\s*\(\s*[^)]*\+|open\s*\(\s*f["\']', re.IGNORECASE),
        "severity": "medium",
        "message": "Potential path traversal vulnerability",
        "cwe": "CWE-22",
        "fix": "Validate and sanitize file paths",
    },
    # Debug code
    {
        "id": "debug-code",
        "pattern": re.compile(r'\b(?:console\.log|print|debugger)\s*\('),
        "severity": "info",
        "message": "Debug code found — remove before production",
        "fix": "Remove debug statements",
    },
    # Insecure HTTP
    {
        "id": "insecure-http",
        "pattern": re.compile(r'http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)', re.IGNORECASE),
        "severity": "medium",
        "message": "Insecure HTTP connection (not HTTPS)",
        "cwe": "CWE-319",
        "fix": "Use HTTPS instead of HTTP",
    },
    # Wildcard CORS
    {
        "id": "wildcard-cors",
        "pattern": re.compile(r'(?:allow_origins|Access-Control-Allow-Origin).*["\']\*["\']', re.IGNORECASE),
        "severity": "medium",
        "message": "Wildcard CORS origin — allows any domain",
        "cwe": "CWE-942",
        "fix": "Restrict CORS to specific trusted origins",
    },
    # Missing CSRF protection
    {
        "id": "no-csrf",
        "pattern": re.compile(r'(?:WTF_CSRF|csrf_protect).*False', re.IGNORECASE),
        "severity": "high",
        "message": "CSRF protection disabled",
        "cwe": "CWE-352",
        "fix": "Enable CSRF protection",
    },
    # Insecure randomness
    {
        "id": "weak-random",
        "pattern": re.compile(r'\brandom\.(?:random|randint|choice)\s*\('),
        "severity": "medium",
        "message": "Non-cryptographic random for security-sensitive context",
        "cwe": "CWE-330",
        "fix": "Use secrets module for security-sensitive random values",
    },
]


class SecurityScanner:
    """Scan code for security vulnerabilities."""

    @classmethod
    def scan_file(cls, filepath: str) -> ScanResult:
        """Scan a single file."""
        result = ScanResult()
        path = Path(filepath)
        if not path.exists():
            return result

        try:
            content = path.read_text(errors="replace")
        except Exception:
            return result

        lines = content.splitlines()
        result.files_scanned = 1

        for rule in RULES:
            for m in rule["pattern"].finditer(content):
                line_num = content[:m.start()].count('\n') + 1
                snippet = lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""

                result.issues.append(SecurityIssue(
                    rule=rule["id"],
                    severity=rule["severity"],
                    message=rule["message"],
                    file=filepath,
                    line=line_num,
                    code_snippet=snippet[:200],
                    cwe=rule.get("cwe", ""),
                    fix_suggestion=rule.get("fix", ""),
                ))

        return result

    @classmethod
    def scan_directory(cls, root: str, extensions: Optional[set[str]] = None) -> ScanResult:
        """Scan all files in a directory."""
        from ..core.context import IGNORE_DIRS, CODE_EXTENSIONS

        if extensions is None:
            extensions = CODE_EXTENSIONS

        result = ScanResult()
        import time
        start = time.monotonic()

        for dirpath, dirnames, filenames in __import__("os").walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for fname in filenames:
                fpath = str(Path(dirpath) / fname)
                ext = Path(fname).suffix.lower()
                if ext in extensions:
                    file_result = cls.scan_file(fpath)
                    result.issues.extend(file_result.issues)
                    result.files_scanned += 1

        result.scan_time_ms = (time.monotonic() - start) * 1000
        return result
