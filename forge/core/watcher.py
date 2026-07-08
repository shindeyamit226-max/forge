"""
File Watcher — monitors file system changes for live re-indexing.
Auto-reindexes the codebase when files change.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent

from .context import IGNORE_DIRS, CODE_EXTENSIONS


class CodebaseEventHandler(FileSystemEventHandler):
    """Handles file system events for codebase changes."""

    def __init__(self, callback: Callable):
        self.callback = callback
        self._debounce: dict[str, float] = {}
        self._debounce_ms = 500

    def _should_process(self, path: str) -> bool:
        """Check if a file should be processed."""
        p = Path(path)

        # Skip ignored directories
        for part in p.parts:
            if part in IGNORE_DIRS or part.startswith("."):
                return False

        # Only process code files
        if p.suffix.lower() not in CODE_EXTENSIONS:
            return False

        # Debounce
        now = time.time() * 1000
        last = self._debounce.get(path, 0)
        if now - last < self._debounce_ms:
            return False
        self._debounce[path] = now

        return True

    def on_modified(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            self.callback("modified", event.src_path)

    def on_created(self, event):
        if not event.is_directory and self._should_process(event.src_path):
            self.callback("created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.callback("deleted", event.src_path)


class FileWatcher:
    """
    Monitors file system changes and triggers re-indexing.
    Runs in a background thread.
    """

    def __init__(self, root: str, on_change: Optional[Callable] = None):
        self.root = Path(root).resolve()
        self.on_change = on_change
        self._observer: Optional[Observer] = None
        self._changed_files: Set[str] = set()
        self._running = False

    def _handle_event(self, event_type: str, filepath: str) -> None:
        """Handle a file system event."""
        rel_path = str(Path(filepath).relative_to(self.root))
        self._changed_files.add(rel_path)

        if self.on_change:
            try:
                self.on_change(event_type, rel_path)
            except Exception:
                pass

    def start(self) -> None:
        """Start watching for changes."""
        if self._running:
            return

        handler = CodebaseEventHandler(self._handle_event)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.root), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._running = True

    def stop(self) -> None:
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._running = False

    def get_changed_files(self) -> Set[str]:
        """Get and clear the set of changed files."""
        changed = self._changed_files.copy()
        self._changed_files.clear()
        return changed

    @property
    def has_changes(self) -> bool:
        return bool(self._changed_files)

    @property
    def is_running(self) -> bool:
        return self._running

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
