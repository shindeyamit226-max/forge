"""
Project context — deep understanding of the codebase.
AST parsing, dependency analysis, file tree, git state.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# File extensions we consider "code"
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".ex",
    ".exs", ".erl", ".hs", ".ml", ".clj", ".lua", ".r", ".m", ".mm",
    ".sql", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd",
}

CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".xml", ".properties", ".gradle", ".cmake", ".mk",
}

DOC_EXTENSIONS = {
    ".md", ".rst", ".txt", ".adoc", ".tex", ".html", ".htm",
}

IGNORE_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "target", "vendor", ".gradle", ".idea", ".vscode",
    "coverage", ".coverage", "htmlcov", ".mypy_cache", ".ruff_cache",
}

IGNORE_FILES = {
    ".DS_Store", "Thumbs.db", ".gitkeep", ".gitattributes",
}

MAX_FILE_SIZE = 1_000_000  # 1MB
MAX_TREE_DEPTH = 8
MAX_FILES_IN_TREE = 500


@dataclass
class FileInfo:
    """Information about a file in the project."""
    path: Path
    language: Optional[str] = None
    size: int = 0
    lines: int = 0
    imports: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)  # Functions, classes, etc.


@dataclass
class ProjectContext:
    """Deep understanding of the project structure and state."""

    root: Path = field(default_factory=lambda: Path.cwd())
    files: dict[str, FileInfo] = field(default_factory=dict)
    languages: dict[str, int] = field(default_factory=dict)  # lang -> file count
    git_branch: Optional[str] = None
    git_status: Optional[str] = None
    has_tests: bool = False
    test_framework: Optional[str] = None
    package_manager: Optional[str] = None
    framework: Optional[str] = None
    entry_points: list[str] = field(default_factory=list)
    readme_summary: Optional[str] = None

    def scan(self, root: Optional[Path] = None) -> None:
        """Scan the project directory and build context."""
        self.root = (root or Path.cwd()).resolve()
        self.files.clear()
        self.languages.clear()

        file_count = 0
        for path in self._walk_project():
            if file_count >= MAX_FILES_IN_TREE:
                break

            rel = str(path.relative_to(self.root))
            ext = path.suffix.lower()

            # Skip ignored
            if path.name in IGNORE_FILES:
                continue
            if any(ig in path.parts for ig in IGNORE_DIRS):
                continue

            try:
                stat = path.stat()
                if stat.st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            lang = self._detect_language(ext)
            if lang:
                info = FileInfo(
                    path=path,
                    language=lang,
                    size=stat.st_size,
                )
                self.files[rel] = info
                self.languages[lang] = self.languages.get(lang, 0) + 1
                file_count += 1

        # Detect project metadata
        self._detect_git()
        self._detect_tests()
        self._detect_package_manager()
        self._detect_framework()
        self._detect_entry_points()
        self._read_readme()

    def _walk_project(self):
        """Walk the project directory tree."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORE_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                yield Path(dirpath) / fname

    @staticmethod
    def _detect_language(ext: str) -> Optional[str]:
        lang_map = {
            ".py": "python", ".pyi": "python",
            ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
            ".ts": "typescript", ".mts": "typescript",
            ".jsx": "react", ".tsx": "react",
            ".rs": "rust", ".go": "go", ".java": "java",
            ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
            ".cs": "csharp", ".rb": "ruby", ".php": "php",
            ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
            ".ex": "elixir", ".exs": "elixir", ".erl": "erlang",
            ".hs": "haskell", ".ml": "ocaml", ".clj": "clojure",
            ".lua": "lua", ".r": "r", ".sql": "sql",
            ".sh": "shell", ".bash": "shell", ".zsh": "shell",
            ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
            ".md": "markdown", ".rst": "rst",
            ".xml": "xml", ".svg": "svg",
        }
        return lang_map.get(ext)

    def _detect_git(self) -> None:
        """Detect git state."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=self.root, timeout=5,
            )
            if result.returncode == 0:
                self.git_branch = result.stdout.strip()

            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=self.root, timeout=5,
            )
            if result.returncode == 0:
                self.git_status = result.stdout.strip()
        except Exception:
            pass

    def _detect_tests(self) -> None:
        """Detect test framework and test files."""
        test_indicators = {
            "pytest": ["pytest.ini", "conftest.py", "pyproject.toml"],
            "jest": ["jest.config.js", "jest.config.ts", "package.json"],
            "mocha": [".mocharc.yml", ".mocharc.js"],
            "cargo": ["Cargo.toml"],
            "go": ["go.mod"],
            "vitest": ["vitest.config.ts", "vitest.config.js"],
        }

        for framework, indicators in test_indicators.items():
            for ind in indicators:
                if (self.root / ind).exists():
                    self.test_framework = framework
                    break

        # Check for test files
        test_patterns = ["test_", "_test.", ".test.", ".spec.", "tests/", "test/"]
        for rel_path in self.files:
            if any(p in rel_path for p in test_patterns):
                self.has_tests = True
                break

    def _detect_package_manager(self) -> None:
        """Detect the package manager."""
        pm_files = {
            "package-lock.json": "npm",
            "yarn.lock": "yarn",
            "pnpm-lock.yaml": "pnpm",
            "Pipfile.lock": "pipenv",
            "poetry.lock": "poetry",
            "requirements.txt": "pip",
            "setup.py": "pip",
            "setup.cfg": "pip",
            "pyproject.toml": "pip",
            "Cargo.lock": "cargo",
            "go.sum": "go",
            "Gemfile.lock": "bundler",
            "composer.lock": "composer",
        }
        for fname, pm in pm_files.items():
            if (self.root / fname).exists():
                self.package_manager = pm
                return

    def _detect_framework(self) -> None:
        """Detect the project framework."""
        indicators = {
            "django": ["manage.py", "wsgi.py"],
            "flask": ["app.py", "wsgi.py"],
            "fastapi": ["main.py"],
            "express": ["app.js", "server.js"],
            "next": ["next.config.js", "next.config.ts"],
            "nuxt": ["nuxt.config.js", "nuxt.config.ts"],
            "react": ["src/App.tsx", "src/App.jsx"],
            "vue": ["vue.config.js"],
            "angular": ["angular.json"],
            "spring": ["pom.xml", "build.gradle"],
            "rails": ["Gemfile", "config/routes.rb"],
            "laravel": ["artisan"],
            "actix": ["Cargo.toml"],
            "gin": ["go.mod"],
        }
        for fw, files in indicators.items():
            if all((self.root / f).exists() for f in files):
                self.framework = fw
                return

    def _detect_entry_points(self) -> None:
        """Detect main entry points."""
        candidates = [
            "main.py", "app.py", "server.py", "manage.py", "cli.py",
            "src/main.py", "src/app.py", "src/index.ts", "src/index.js",
            "main.go", "main.rs", "cmd/main.go",
        ]
        for c in candidates:
            if (self.root / c).exists():
                self.entry_points.append(c)

    def _read_readme(self) -> None:
        """Read and summarize the README."""
        for name in ["README.md", "README.rst", "README.txt", "readme.md"]:
            path = self.root / name
            if path.exists():
                try:
                    content = path.read_text(errors="ignore")
                    # Take first 500 chars as summary
                    self.readme_summary = content[:500].strip()
                except Exception:
                    pass
                return

    def file_tree(self, max_depth: int = MAX_TREE_DEPTH) -> str:
        """Generate a formatted file tree string."""
        lines = [f"{self.root.name}/"]
        self._build_tree(self.root, lines, prefix="", depth=0, max_depth=max_depth)
        return "\n".join(lines)

    def _build_tree(
        self, directory: Path, lines: list[str],
        prefix: str, depth: int, max_depth: int,
    ) -> None:
        if depth >= max_depth:
            return

        try:
            entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return

        entries = [
            e for e in entries
            if e.name not in IGNORE_DIRS and not e.name.startswith(".")
        ]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir():
                # Count children
                try:
                    child_count = sum(1 for _ in entry.iterdir())
                except PermissionError:
                    child_count = 0
                lines.append(f"{prefix}{connector}{entry.name}/ ({child_count})")
                self._build_tree(entry, lines, child_prefix, depth + 1, max_depth)
            else:
                size = ""
                try:
                    s = entry.stat().st_size
                    if s > 1024 * 1024:
                        size = f" ({s // (1024*1024)}MB)"
                    elif s > 1024:
                        size = f" ({s // 1024}KB)"
                except OSError:
                    pass
                lines.append(f"{prefix}{connector}{entry.name}{size}")

    def summary(self) -> str:
        """Generate a human-readable project summary."""
        parts = [f"Project root: {self.root}"]

        if self.git_branch:
            parts.append(f"Git branch: {self.git_branch}")

        if self.languages:
            top = sorted(self.languages.items(), key=lambda x: -x[1])[:5]
            lang_str = ", ".join(f"{l} ({c})" for l, c in top)
            parts.append(f"Languages: {lang_str}")

        if self.framework:
            parts.append(f"Framework: {self.framework}")
        if self.package_manager:
            parts.append(f"Package manager: {self.package_manager}")
        if self.test_framework:
            parts.append(f"Test framework: {self.test_framework}")
        if self.has_tests:
            parts.append("Has tests: yes")
        if self.entry_points:
            parts.append(f"Entry points: {', '.join(self.entry_points)}")

        parts.append(f"Total files: {len(self.files)}")

        if self.readme_summary:
            parts.append(f"\nREADME:\n{self.readme_summary}")

        return "\n".join(parts)

    def get_relevant_files(self, query: str, max_files: int = 20) -> list[str]:
        """Get files most relevant to a query (simple keyword matching)."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for rel_path, info in self.files.items():
            score = 0
            path_lower = rel_path.lower()

            # Exact word matches in path
            for word in query_words:
                if word in path_lower:
                    score += 3

            # Language relevance
            if info.language:
                if info.language in query_lower:
                    score += 2

            # Prefer shorter paths (more specific)
            score -= len(Path(rel_path).parts) * 0.1

            if score > 0:
                scored.append((score, rel_path))

        scored.sort(reverse=True)
        return [path for _, path in scored[:max_files]]
