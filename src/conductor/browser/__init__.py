"""
Browser automation and session management.
"""

from .auth import AuthenticationFlow, AuthStatus
from .session import SessionManager
from .submission import TaskSubmitter, SubmissionResult

__all__ = [
    "AuthenticationFlow",
    "AuthStatus",
    "SessionManager",
    "TaskSubmitter",
    "SubmissionResult",
]
