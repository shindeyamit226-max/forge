"""
Security Scanner — detect vulnerabilities, anti-patterns, and security issues.
Checks: SQL injection, XSS, hardcoded secrets, insecure crypto, dependency vulns.
"""

from .scanner import SecurityScanner, SecurityIssue, ScanResult

__all__ = ["SecurityScanner", "SecurityIssue", "ScanResult"]
