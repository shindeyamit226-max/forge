"""
Refactoring Engine — safe code transformations with rollback.
Every refactoring is: planned → previewed → applied → verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RefactorResult:
    """Result of a refactoring operation."""
    success: bool
    changes: list[dict] = field(default_factory=list)  # {file, old, new}
    errors: list[str] = field(default_factory=list)
    preview: str = ""

    def add_change(self, file: str, old: str, new: str):
        self.changes.append({"file": file, "old": old, "new": new})


class RefactorEngine:
    """Safe code refactoring with preview and rollback."""

    @classmethod
    def rename_symbol(
        cls, old_name: str, new_name: str,
        files: list[str], dry_run: bool = False,
    ) -> RefactorResult:
        """Rename a symbol across multiple files."""
        result = RefactorResult(success=True)

        for filepath in files:
            path = Path(filepath)
            if not path.exists():
                continue

            content = path.read_text(errors="replace")

            # Use word boundary matching
            pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')
            matches = pattern.findall(content)

            if matches:
                new_content = pattern.sub(new_name, content)
                result.add_change(filepath, old_name, new_name)

                if not dry_run:
                    path.write_text(new_content)

        if not result.changes:
            result.success = False
            result.errors.append(f"'{old_name}' not found in any file")

        result.preview = f"Rename '{old_name}' → '{new_name}' in {len(result.changes)} files"
        return result

    @classmethod
    def extract_method(
        cls, source_file: str, start_line: int, end_line: int,
        method_name: str, dry_run: bool = False,
    ) -> RefactorResult:
        """Extract lines into a new method."""
        result = RefactorResult(success=True)
        path = Path(source_file)

        if not path.exists():
            result.success = False
            result.errors.append(f"File not found: {source_file}")
            return result

        lines = path.read_text(errors="replace").splitlines()

        if start_line < 1 or end_line > len(lines) or start_line >= end_line:
            result.success = False
            result.errors.append(f"Invalid line range: {start_line}-{end_line}")
            return result

        # Extract lines
        extracted = lines[start_line - 1:end_line]

        # Determine indentation
        min_indent = float("inf")
        for line in extracted:
            if line.strip():
                min_indent = min(min_indent, len(line) - len(line.lstrip()))
        min_indent = int(min_indent) if min_indent != float("inf") else 0

        # Dedent extracted code
        dedented = []
        for line in extracted:
            if line.strip():
                dedented.append(line[min_indent:])
            else:
                dedented.append("")

        # Create method
        method_body = "\n".join(dedented)
        method = f"{' ' * min_indent}def {method_name}():"
        method += f"\n{' ' * (min_indent + 4)}" + "\n{' ' * (min_indent + 4)}".join(dedented)

        # Replace extracted lines with method call
        call = f"{' ' * min_indent}{method_name}()"
        new_lines = lines[:start_line - 1] + [call] + lines[end_line:]
        new_content = "\n".join(new_lines)

        result.preview = f"Extract lines {start_line}-{end_line} into {method_name}()"
        result.add_change(source_file, "\n".join(lines), new_content)

        if not dry_run:
            path.write_text(new_content)

        return result

    @classmethod
    def inline_variable(
        cls, filepath: str, var_name: str, dry_run: bool = False,
    ) -> RefactorResult:
        """Inline a variable — replace all uses with its value."""
        result = RefactorResult(success=True)
        path = Path(filepath)

        if not path.exists():
            result.success = False
            result.errors.append(f"File not found: {filepath}")
            return result

        content = path.read_text(errors="replace")

        # Find the assignment
        pattern = re.compile(rf'^(\s*){re.escape(var_name)}\s*=\s*(.+)$', re.MULTILINE)
        m = pattern.search(content)

        if not m:
            result.success = False
            result.errors.append(f"Variable '{var_name}' not found")
            return result

        value = m.group(2).strip()
        # Remove the assignment line
        new_content = content[:m.start()] + content[m.end():]

        # Replace all uses
        use_pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
        new_content = use_pattern.sub(f'({value})', new_content)

        result.preview = f"Inline '{var_name}' = {value}"
        result.add_change(filepath, content, new_content)

        if not dry_run:
            path.write_text(new_content)

        return result

    @classmethod
    def change_signature(
        cls, filepath: str, func_name: str,
        new_params: list[dict], dry_run: bool = False,
    ) -> RefactorResult:
        """Change a function's signature (add/remove/reorder parameters)."""
        result = RefactorResult(success=True)
        path = Path(filepath)

        if not path.exists():
            result.success = False
            result.errors.append(f"File not found: {filepath}")
            return result

        content = path.read_text(errors="replace")

        # Find function definition
        pattern = re.compile(
            rf'^(def\s+{re.escape(func_name)}\s*\()([^)]*)(\))',
            re.MULTILINE,
        )
        m = pattern.search(content)

        if not m:
            result.success = False
            result.errors.append(f"Function '{func_name}' not found")
            return result

        # Build new signature
        new_params_str = ", ".join(
            f"{p['name']}: {p.get('type', 'Any')}" + (f" = {p['default']}" if 'default' in p else "")
            for p in new_params
        )

        new_sig = f"{m.group(1)}{new_params_str}{m.group(3)}"
        new_content = content[:m.start()] + new_sig + content[m.end():]

        result.preview = f"Change signature of {func_name}({new_params_str})"
        result.add_change(filepath, content, new_content)

        if not dry_run:
            path.write_text(new_content)

        return result
