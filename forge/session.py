"""
Session management — history, persistence, resume.
Your conversations survive restarts.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class SessionMessage:
    """A message in the session history."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Session:
    """A conversation session with persistence."""
    id: str
    messages: list[SessionMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
    files_modified: list[str] = field(default_factory=list)

    def add_message(self, role: str, content: str, **kwargs) -> None:
        self.messages.append(SessionMessage(role=role, content=content, **kwargs))
        self.updated_at = time.time()

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def duration(self) -> float:
        return self.updated_at - self.created_at

    def save(self, path: Path) -> None:
        """Persist session to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "files_modified": self.files_modified,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "tool_calls": m.tool_calls,
                    "tool_call_id": m.tool_call_id,
                    "metadata": m.metadata,
                }
                for m in self.messages
            ],
        }
        path.write_text(json.dumps(data, indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> Optional[Session]:
        """Load session from disk."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            session = cls(
                id=data["id"],
                created_at=data.get("created_at", 0),
                updated_at=data.get("updated_at", 0),
                metadata=data.get("metadata", {}),
                files_modified=data.get("files_modified", []),
            )
            for m in data.get("messages", []):
                session.messages.append(SessionMessage(
                    role=m["role"],
                    content=m["content"],
                    timestamp=m.get("timestamp", 0),
                    tool_calls=m.get("tool_calls"),
                    tool_call_id=m.get("tool_call_id"),
                    metadata=m.get("metadata", {}),
                ))
            return session
        except Exception:
            return None


class SessionManager:
    """Manages multiple sessions with persistence."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create(self, session_id: Optional[str] = None) -> Session:
        """Create a new session."""
        if not session_id:
            session_id = f"session_{int(time.time())}"
        session = Session(id=session_id)
        return session

    def save(self, session: Session) -> None:
        """Save a session."""
        path = self.sessions_dir / f"{session.id}.json"
        session.save(path)

    def load(self, session_id: str) -> Optional[Session]:
        """Load a session by ID."""
        path = self.sessions_dir / f"{session_id}.json"
        return Session.load(path)

    def list_sessions(self) -> list[dict]:
        """List all saved sessions."""
        sessions = []
        for path in sorted(self.sessions_dir.glob("session_*.json"), reverse=True):
            session = Session.load(path)
            if session:
                sessions.append({
                    "id": session.id,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "messages": session.message_count,
                    "files": len(session.files_modified),
                })
        return sessions[:50]  # Last 50 sessions

    def latest(self) -> Optional[Session]:
        """Load the most recent session."""
        sessions = self.list_sessions()
        if sessions:
            return self.load(sessions[0]["id"])
        return None

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        path = self.sessions_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False
