"""
Tests for TUI components.
"""

import pytest
from conductor.tui.app import ConductorTUI, TaskQueuePanel, ExecutionPanel, MetricsPanel
from conductor.tasks.models import Task, TaskList, TaskStatus, Priority


@pytest.fixture
def sample_tasks():
    """Create sample tasks for testing."""
    return [
        Task(
            id="AUTH-001",
            name="Add Auth Tests",
            prompt="Create unit tests",
            expected_deliverable="test_auth.py",
            priority=Priority.HIGH,
            status=TaskStatus.COMPLETED,
        ),
        Task(
            id="DOC-001",
            name="Update Documentation",
            prompt="Update docs",
            expected_deliverable="docs/api.md",
            priority=Priority.MEDIUM,
            status=TaskStatus.RUNNING,
        ),
        Task(
            id="REFACTOR-001",
            name="Refactor Code",
            prompt="Refactor module",
            expected_deliverable="refactored_module.py",
            priority=Priority.LOW,
            status=TaskStatus.PENDING,
        ),
    ]


def test_task_list_creation(sample_tasks):
    """Test creating a task list."""
    task_list = TaskList(tasks=sample_tasks)

    assert len(task_list) == 3
    assert task_list.tasks[0].id == "AUTH-001"
    assert task_list.tasks[1].id == "DOC-001"
    assert task_list.tasks[2].id == "REFACTOR-001"


def test_task_queue_panel_initialization(sample_tasks):
    """Test task queue panel initialization."""
    task_list = TaskList(tasks=sample_tasks)
    panel = TaskQueuePanel(task_list)

    assert panel.task_list == task_list
    assert panel.current_task_id is None


def test_execution_panel_progress_bar():
    """Test progress bar creation."""
    panel = ExecutionPanel()

    # Test 0% progress
    bar_0 = panel._create_progress_bar(0.0)
    assert "0%" in bar_0
    assert "░" in bar_0

    # Test 50% progress
    bar_50 = panel._create_progress_bar(0.5)
    assert "50%" in bar_50
    assert "█" in bar_50
    assert "░" in bar_50

    # Test 100% progress
    bar_100 = panel._create_progress_bar(1.0)
    assert "100%" in bar_100
    assert "█" in bar_100


def test_execution_panel_status_text():
    """Test status text coloring."""
    panel = ExecutionPanel()

    # Test each status
    for status in TaskStatus:
        text = panel._get_status_text(status)
        assert status.value in text


def test_metrics_panel_initialization():
    """Test metrics panel initialization."""
    panel = MetricsPanel()

    assert panel.total_tasks == 0
    assert panel.completed == 0
    assert panel.failed == 0
    assert panel.skipped == 0


def test_metrics_panel_update():
    """Test updating metrics."""
    panel = MetricsPanel()

    panel.update_metrics(
        total=10, completed=7, failed=2, skipped=1, avg_time=120.0, total_time=1200.0
    )

    assert panel.total_tasks == 10
    assert panel.completed == 7
    assert panel.failed == 2
    assert panel.skipped == 1
    assert panel.avg_time == 120.0
    assert panel.total_time == 1200.0


def test_conductor_tui_initialization(sample_tasks):
    """Test TUI app initialization."""
    task_list = TaskList(tasks=sample_tasks)
    app = ConductorTUI(task_list=task_list)

    assert app.task_list == task_list
    assert app.TITLE == "🎭 Conductor - Claude Code Orchestration"
