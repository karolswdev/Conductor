"""
Session management for tracking Claude Code sessions.
"""

import logging
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path
import json

from ..tasks.models import Task


logger = logging.getLogger(__name__)


class SessionInfo:
    """Information about a Claude Code session."""

    def __init__(
        self,
        session_id: str,
        task_id: str,
        branch_name: Optional[str] = None,
        started_at: Optional[datetime] = None,
        url: Optional[str] = None,
    ):
        self.session_id = session_id
        self.task_id = task_id
        self.branch_name = branch_name
        self.started_at = started_at or datetime.now()
        self.url = url

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "branch_name": self.branch_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SessionInfo":
        """Create from dictionary."""
        started_at = None
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])

        return cls(
            session_id=data["session_id"],
            task_id=data["task_id"],
            branch_name=data.get("branch_name"),
            started_at=started_at,
            url=data.get("url"),
        )


class SessionManager:
    """
    Manages Claude Code sessions and tracks branch names.

    Implements FR-033 and FR-034:
    - Maintains rolling log of ALL branch names created
    - Timestamps and persists branch information
    """

    def __init__(self, log_file: Optional[Path] = None):
        """
        Initialize session manager.

        Args:
            log_file: Path to session log file. If None, uses default location.
        """
        self.log_file = log_file or Path.home() / ".conductor" / "sessions.jsonl"
        self.sessions: List[SessionInfo] = []
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        """Ensure log file directory exists."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()

    def add_session(
        self,
        session_id: str,
        task_id: str,
        branch_name: Optional[str] = None,
        url: Optional[str] = None,
    ) -> SessionInfo:
        """
        Add a new session.

        Args:
            session_id: Claude Code session ID
            task_id: Task ID associated with this session
            branch_name: Git branch name
            url: Session URL

        Returns:
            SessionInfo object
        """
        session = SessionInfo(
            session_id=session_id,
            task_id=task_id,
            branch_name=branch_name,
            url=url,
        )

        self.sessions.append(session)
        self._persist_session(session)

        logger.info(f"Added session {session_id} for task {task_id}")
        if branch_name:
            logger.info(f"  Branch: {branch_name}")

        return session

    def update_session(
        self,
        session_id: str,
        branch_name: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Optional[SessionInfo]:
        """
        Update session information.

        Args:
            session_id: Session ID to update
            branch_name: New branch name
            url: New URL

        Returns:
            Updated SessionInfo or None if not found
        """
        session = self.get_session(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found")
            return None

        if branch_name:
            session.branch_name = branch_name
        if url:
            session.url = url

        self._persist_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """
        Get session by ID.

        Args:
            session_id: Session ID to find

        Returns:
            SessionInfo or None if not found
        """
        for session in self.sessions:
            if session.session_id == session_id:
                return session
        return None

    def get_sessions_for_task(self, task_id: str) -> List[SessionInfo]:
        """
        Get all sessions for a task.

        Args:
            task_id: Task ID

        Returns:
            List of SessionInfo objects
        """
        return [s for s in self.sessions if s.task_id == task_id]

    def get_all_branches(self) -> List[str]:
        """
        Get all branch names ever created.

        Returns:
            List of branch names
        """
        branches = [s.branch_name for s in self.sessions if s.branch_name]
        # Also load from persistent log
        branches.extend(self._load_all_branches_from_log())
        return list(set(branches))  # Deduplicate

    def _persist_session(self, session: SessionInfo) -> None:
        """
        Persist session to log file (append-only).

        Args:
            session: Session to persist
        """
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(session.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist session: {e}")

    def _load_all_branches_from_log(self) -> List[str]:
        """
        Load all branch names from persistent log.

        Returns:
            List of branch names
        """
        branches = []

        try:
            if not self.log_file.exists():
                return branches

            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if branch_name := data.get("branch_name"):
                            branches.append(branch_name)
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Failed to load branches from log: {e}")

        return branches

    def load_sessions(self) -> None:
        """Load sessions from persistent log."""
        try:
            if not self.log_file.exists():
                return

            self.sessions = []
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        session = SessionInfo.from_dict(data)
                        self.sessions.append(session)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse session line: {e}")

            logger.info(f"Loaded {len(self.sessions)} sessions from log")

        except Exception as e:
            logger.error(f"Failed to load sessions: {e}")
