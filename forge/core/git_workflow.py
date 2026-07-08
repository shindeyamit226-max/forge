"""
Git Workflow Manager — intelligent git operations for agentic coding.
Auto-commit, branch management, blame, history analysis, PR creation.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GitStatus:
    """Current git status."""
    branch: str = ""
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    staged: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    conflicted: list[str] = field(default_factory=list)
    is_clean: bool = True

    def summary(self) -> str:
        parts = [f"Branch: {self.branch}"]
        if self.upstream:
            parts.append(f"Upstream: {self.upstream}")
        if self.ahead:
            parts.append(f"Ahead: {self.ahead}")
        if self.behind:
            parts.append(f"Behind: {self.behind}")
        if self.staged:
            parts.append(f"Staged: {len(self.staged)}")
        if self.modified:
            parts.append(f"Modified: {len(self.modified)}")
        if self.untracked:
            parts.append(f"Untracked: {len(self.untracked)}")
        if self.deleted:
            parts.append(f"Deleted: {len(self.deleted)}")
        if self.conflicted:
            parts.append(f"Conflicted: {len(self.conflicted)}")
        if self.is_clean:
            parts.append("Working tree clean")
        return " | ".join(parts)


@dataclass
class GitCommit:
    """A git commit."""
    hash: str
    author: str
    date: str
    message: str
    files: list[str] = field(default_factory=list)


@dataclass
class GitBlame:
    """Blame information for a line."""
    line: int
    hash: str
    author: str
    content: str


class GitWorkflow:
    """
    Intelligent git operations for agentic coding.
    Provides high-level git operations that the agent can use.
    """

    def __init__(self, cwd: str = "."):
        self.cwd = Path(cwd).resolve()

    async def _run(self, *args: str, check: bool = True) -> tuple[str, str, int]:
        """Run a git command."""
        cmd = ["git"] + list(args)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return (
            stdout.decode(errors="replace").strip(),
            stderr.decode(errors="replace").strip(),
            proc.returncode or 0,
        )

    async def status(self) -> GitStatus:
        """Get comprehensive git status."""
        status = GitStatus()

        # Get branch
        out, _, rc = await self._run("rev-parse", "--abbrev-ref", "HEAD")
        if rc == 0:
            status.branch = out

        # Get upstream
        out, _, rc = await self._run("rev-parse", "--abbrev-ref", "@{upstream}")
        if rc == 0:
            status.upstream = out

        # Get ahead/behind counts
        out, _, rc = await self._run("rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        if rc == 0 and out:
            parts = out.split()
            if len(parts) == 2:
                status.ahead = int(parts[0])
                status.behind = int(parts[1])

        # Get file statuses
        out, _, _ = await self._run("status", "--porcelain")
        for line in out.splitlines():
            if not line.strip():
                continue
            index_status = line[0]
            work_status = line[1]
            filename = line[3:].strip()

            if index_status == "A" or index_status == "M":
                status.staged.append(filename)
            elif work_status == "M":
                status.modified.append(filename)
            elif work_status == "D" or index_status == "D":
                status.deleted.append(filename)
            elif index_status == "?":
                status.untracked.append(filename)
            elif index_status == "U" or work_status == "U":
                status.conflicted.append(filename)

        status.is_clean = not (status.staged or status.modified or status.untracked or status.deleted)
        return status

    async def diff(self, staged: bool = False, file: Optional[str] = None) -> str:
        """Get diff of changes."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file:
            args.append(file)
        out, _, _ = await self._run(*args)
        return out

    async def log(self, count: int = 10, file: Optional[str] = None) -> list[GitCommit]:
        """Get recent commits."""
        args = [
            "log", f"-{count}",
            "--pretty=format:%H|%an|%ai|%s",
            "--name-only",
        ]
        if file:
            args.extend(["--", file])

        out, _, _ = await self._run(*args)
        commits = []
        current = None

        for line in out.splitlines():
            if "|" in line and len(line.split("|")) >= 4:
                parts = line.split("|", 3)
                current = GitCommit(
                    hash=parts[0][:8],
                    author=parts[1],
                    date=parts[2],
                    message=parts[3],
                )
                commits.append(current)
            elif current and line.strip():
                current.files.append(line.strip())

        return commits

    async def blame(self, file: str, line_start: int = 1, line_end: int = 0) -> list[GitBlame]:
        """Get blame information for a file."""
        args = ["blame", "-L", f"{line_start},{line_end}" if line_end else f"{line_start},", "--porcelain", file]
        out, _, rc = await self._run(*args)

        blames = []
        current = {}
        for line in out.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2 and len(parts[0]) == 40:
                current["hash"] = parts[0][:8]
            elif line.startswith("author "):
                current["author"] = line[7:]
            elif line.startswith("\t"):
                current["content"] = line[1:]
                if "hash" in current and "author" in current:
                    blames.append(GitBlame(
                        line=len(blames) + line_start,
                        hash=current.get("hash", ""),
                        author=current.get("author", ""),
                        content=current.get("content", ""),
                    ))
                current = {}

        return blames

    async def stage(self, files: list[str]) -> bool:
        """Stage files."""
        _, _, rc = await self._run("add", *files)
        return rc == 0

    async def unstage(self, files: list[str]) -> bool:
        """Unstage files."""
        _, _, rc = await self._run("reset", "HEAD", "--", *files)
        return rc == 0

    async def commit(self, message: str, files: Optional[list[str]] = None) -> tuple[bool, str]:
        """Create a commit. If files provided, stages them first."""
        if files:
            await self.stage(files)

        out, err, rc = await self._run("commit", "-m", message)
        if rc == 0:
            return True, out
        return False, err or out

    async def auto_commit(
        self,
        message: str,
        files: Optional[list[str]] = None,
    ) -> tuple[bool, str]:
        """
        Smart auto-commit for agent changes.
        Stages modified files, creates a descriptive commit.
        """
        if not files:
            # Auto-detect changed files
            st = await self.status()
            files = st.modified + st.staged + st.untracked
            # Filter to only actually changed files
            files = [f for f in files if Path(self.cwd / f).exists() or f in st.deleted]

        if not files:
            return False, "No changes to commit"

        return await self.commit(message, files)

    async def create_branch(self, name: str, checkout: bool = True) -> bool:
        """Create a new branch."""
        if checkout:
            _, _, rc = await self._run("checkout", "-b", name)
        else:
            _, _, rc = await self._run("branch", name)
        return rc == 0

    async def checkout(self, branch: str) -> bool:
        """Switch to a branch."""
        _, _, rc = await self._run("checkout", branch)
        return rc == 0

    async def stash(self, message: str = "") -> bool:
        """Stash current changes."""
        args = ["stash"]
        if message:
            args.extend(["-m", message])
        _, _, rc = await self._run(*args)
        return rc == 0

    async def stash_pop(self) -> bool:
        """Pop the latest stash."""
        _, _, rc = await self._run("stash", "pop")
        return rc == 0

    async def merge(self, branch: str) -> tuple[bool, str]:
        """Merge a branch."""
        out, err, rc = await self._run("merge", branch)
        if rc == 0:
            return True, out
        return False, err or out

    async def rebase(self, branch: str) -> tuple[bool, str]:
        """Rebase onto a branch."""
        out, err, rc = await self._run("rebase", branch)
        if rc == 0:
            return True, out
        return False, err or out

    async def get_changed_files(self, ref: str = "HEAD") -> list[str]:
        """Get files changed since a ref."""
        out, _, rc = await self._run("diff", "--name-only", ref)
        if rc == 0:
            return [f for f in out.splitlines() if f.strip()]
        return []

    async def get_recent_changes_summary(self, count: int = 5) -> str:
        """Get a summary of recent changes."""
        commits = await self.log(count)
        lines = [f"Recent {len(commits)} commits:"]
        for c in commits:
            files_str = f" ({len(c.files)} files)" if c.files else ""
            lines.append(f"  {c.hash} {c.message}{files_str}")
        return "\n".join(lines)

    async def is_git_repo(self) -> bool:
        """Check if we're in a git repo."""
        _, _, rc = await self._run("rev-parse", "--git-dir")
        return rc == 0
