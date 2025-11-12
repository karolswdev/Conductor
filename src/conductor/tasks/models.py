"""
Task data models using Pydantic for validation.
"""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Priority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PRStrategy(str, Enum):
    """PR creation strategy."""

    AGGRESSIVE = "aggressive"  # 30 minutes
    NORMAL = "normal"  # 60 minutes
    PATIENT = "patient"  # 120 minutes
    MANUAL = "manual"  # Manual intervention required


class RetryPolicy(BaseModel):
    """Retry policy configuration."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_factor: float = Field(default=2.0, ge=1.0, le=5.0)
    initial_delay: float = Field(default=5.0, ge=1.0)
    max_delay: float = Field(default=300.0, ge=10.0)
    jitter: float = Field(default=0.2, ge=0.0, le=0.5)


class Task(BaseModel):
    """
    A task to be executed by Conductor.

    Attributes:
        id: Unique identifier for the task
        name: Short display name (max 20 chars recommended)
        prompt: Full prompt to send to Claude Code
        expected_deliverable: Description of what should be produced
        priority: Task priority level
        auto_pr_timeout: Seconds before auto-creating PR
        pr_strategy: Strategy for PR creation timing
        retry_policy: Retry configuration
        dependencies: List of task IDs that must complete first
        repository: GitHub repository (owner/repo format)
        status: Current execution status
        created_at: Timestamp when task was created
        started_at: Timestamp when task started executing
        completed_at: Timestamp when task completed
        session_id: Claude Code session ID
        branch_name: Git branch created for this task
        pr_url: Pull request URL if created
        error_message: Error message if task failed
        retry_count: Number of retries attempted
    """

    # Required fields
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    prompt: str = Field(..., min_length=1)
    expected_deliverable: str = Field(..., min_length=1)

    # Optional configuration
    priority: Priority = Field(default=Priority.MEDIUM)
    auto_pr_timeout: int = Field(default=1800, ge=60, le=7200)
    pr_strategy: PRStrategy = Field(default=PRStrategy.NORMAL)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    dependencies: List[str] = Field(default_factory=list)
    repository: Optional[str] = Field(default=None, pattern=r"^[\w-]+/[\w-]+$")

    # Runtime state
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    session_id: Optional[str] = None
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = Field(default=0, ge=0)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate task ID format."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Task ID must contain only alphanumeric characters, hyphens, and underscores")
        return v

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, v: List[str]) -> List[str]:
        """Validate dependency list."""
        if len(v) != len(set(v)):
            raise ValueError("Dependencies must be unique")
        return v

    @property
    def display_name(self) -> str:
        """Get truncated name for display."""
        if len(self.name) <= 20:
            return self.name
        return self.name[:17] + "..."

    @property
    def pr_timeout_seconds(self) -> int:
        """Get PR timeout based on strategy."""
        strategy_timeouts = {
            PRStrategy.AGGRESSIVE: 1800,  # 30 min
            PRStrategy.NORMAL: 3600,  # 60 min
            PRStrategy.PATIENT: 7200,  # 120 min
            PRStrategy.MANUAL: 0,  # No timeout
        }
        return strategy_timeouts.get(self.pr_strategy, self.auto_pr_timeout)

    def start(self) -> None:
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self, session_id: Optional[str] = None, branch_name: Optional[str] = None) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        if session_id:
            self.session_id = session_id
        if branch_name:
            self.branch_name = branch_name

    def fail(self, error: str) -> None:
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error

    def skip(self) -> None:
        """Mark task as skipped."""
        self.status = TaskStatus.SKIPPED
        self.completed_at = datetime.now()

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self.retry_count += 1

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.retry_policy.max_attempts


class TaskList(BaseModel):
    """Collection of tasks with validation."""

    tasks: List[Task] = Field(default_factory=list)

    @field_validator("tasks")
    @classmethod
    def validate_unique_ids(cls, v: List[Task]) -> List[Task]:
        """Ensure all task IDs are unique."""
        ids = [task.id for task in v]
        if len(ids) != len(set(ids)):
            raise ValueError("All task IDs must be unique")
        return v

    @field_validator("tasks")
    @classmethod
    def validate_dependencies(cls, v: List[Task]) -> List[Task]:
        """Validate that all dependencies exist and no circular deps."""
        task_ids = {task.id for task in v}

        # Check all dependencies exist
        for task in v:
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise ValueError(f"Task {task.id} depends on non-existent task {dep_id}")

        # Check for circular dependencies using DFS
        def has_cycle(task_id: str, visited: set, rec_stack: set, dep_map: dict) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            for dep in dep_map.get(task_id, []):
                if dep not in visited:
                    if has_cycle(dep, visited, rec_stack, dep_map):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(task_id)
            return False

        dep_map = {task.id: task.dependencies for task in v}
        visited: set = set()
        rec_stack: set = set()

        for task in v:
            if task.id not in visited:
                if has_cycle(task.id, visited, rec_stack, dep_map):
                    raise ValueError(f"Circular dependency detected involving task {task.id}")

        return v

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        return [task for task in self.tasks if task.status == TaskStatus.PENDING]

    def get_runnable_tasks(self) -> List[Task]:
        """Get tasks that can be run (pending with all dependencies met)."""
        runnable = []
        for task in self.tasks:
            if task.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are completed
            deps_met = all(
                self.get_task(dep_id).status == TaskStatus.COMPLETED if self.get_task(dep_id) else False
                for dep_id in task.dependencies
            )

            if deps_met:
                runnable.append(task)

        return runnable

    def add_task(self, task: Task) -> None:
        """Add a task to the list."""
        self.tasks.append(task)

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self):
        return iter(self.tasks)
