"""
Tests for task loading from YAML files.
"""

import pytest
from pathlib import Path
from conductor.tasks.loader import TaskLoader, TaskLoadError
from conductor.tasks.models import Task, Priority, PRStrategy


def test_load_simple_task():
    """Test loading a simple task from YAML."""
    yaml_content = """
tasks:
  - id: "TEST-001"
    name: "Test Task"
    prompt: "Do something"
    expected_deliverable: "Something done"
"""

    task_list = TaskLoader.load_from_yaml_string(yaml_content)

    assert len(task_list) == 1
    task = task_list.tasks[0]
    assert task.id == "TEST-001"
    assert task.name == "Test Task"
    assert task.prompt == "Do something"
    assert task.expected_deliverable == "Something done"
    assert task.priority == Priority.MEDIUM  # Default


def test_load_task_with_all_fields():
    """Test loading a task with all fields specified."""
    yaml_content = """
tasks:
  - id: "TASK-001"
    name: "Complex Task"
    prompt: "Do complex thing"
    expected_deliverable: "Complex thing done"
    priority: high
    auto_pr_timeout: 3600
    pr_strategy: aggressive
    retry_policy:
      max_attempts: 5
      backoff_factor: 1.5
      initial_delay: 10.0
      max_delay: 600.0
      jitter: 0.3
    dependencies:
      - "OTHER-001"
    repository: "user/repo"
"""

    task_list = TaskLoader.load_from_yaml_string(yaml_content)

    assert len(task_list) == 1
    task = task_list.tasks[0]
    assert task.id == "TASK-001"
    assert task.priority == Priority.HIGH
    assert task.pr_strategy == PRStrategy.AGGRESSIVE
    assert task.auto_pr_timeout == 3600
    assert task.retry_policy.max_attempts == 5
    assert task.retry_policy.backoff_factor == 1.5
    assert task.dependencies == ["OTHER-001"]
    assert task.repository == "user/repo"


def test_load_multiple_tasks():
    """Test loading multiple tasks."""
    yaml_content = """
tasks:
  - id: "TASK-001"
    name: "First Task"
    prompt: "Do first thing"
    expected_deliverable: "First thing done"
  - id: "TASK-002"
    name: "Second Task"
    prompt: "Do second thing"
    expected_deliverable: "Second thing done"
  - id: "TASK-003"
    name: "Third Task"
    prompt: "Do third thing"
    expected_deliverable: "Third thing done"
"""

    task_list = TaskLoader.load_from_yaml_string(yaml_content)

    assert len(task_list) == 3
    assert task_list.tasks[0].id == "TASK-001"
    assert task_list.tasks[1].id == "TASK-002"
    assert task_list.tasks[2].id == "TASK-003"


def test_load_tasks_with_dependencies():
    """Test loading tasks with dependencies."""
    yaml_content = """
tasks:
  - id: "BASE-001"
    name: "Base Task"
    prompt: "Do base thing"
    expected_deliverable: "Base thing done"
  - id: "DEPENDENT-001"
    name: "Dependent Task"
    prompt: "Do dependent thing"
    expected_deliverable: "Dependent thing done"
    dependencies:
      - "BASE-001"
"""

    task_list = TaskLoader.load_from_yaml_string(yaml_content)

    assert len(task_list) == 2
    dependent = task_list.get_task("DEPENDENT-001")
    assert dependent.dependencies == ["BASE-001"]


def test_invalid_yaml_syntax():
    """Test that invalid YAML syntax raises TaskLoadError."""
    yaml_content = """
tasks:
  - id: "TASK-001
    name: "Broken Task"
"""

    with pytest.raises(TaskLoadError, match="Invalid YAML syntax"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_missing_tasks_key():
    """Test that missing 'tasks' key raises TaskLoadError."""
    yaml_content = """
items:
  - id: "TASK-001"
"""

    with pytest.raises(TaskLoadError, match="must contain a 'tasks' key"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_empty_task_list():
    """Test that empty task list raises TaskLoadError."""
    yaml_content = """
tasks: []
"""

    with pytest.raises(TaskLoadError, match="Task list is empty"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_duplicate_task_ids():
    """Test that duplicate task IDs raise TaskLoadError."""
    yaml_content = """
tasks:
  - id: "TASK-001"
    name: "First Task"
    prompt: "Do thing"
    expected_deliverable: "Thing done"
  - id: "TASK-001"
    name: "Duplicate Task"
    prompt: "Do other thing"
    expected_deliverable: "Other thing done"
"""

    with pytest.raises(TaskLoadError, match="must be unique"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_missing_required_field():
    """Test that missing required fields raise TaskLoadError."""
    yaml_content = """
tasks:
  - id: "TASK-001"
    name: "Incomplete Task"
"""

    with pytest.raises(TaskLoadError, match="Validation failed"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_circular_dependency():
    """Test that circular dependencies are detected."""
    yaml_content = """
tasks:
  - id: "TASK-001"
    name: "First Task"
    prompt: "Do first thing"
    expected_deliverable: "First thing done"
    dependencies:
      - "TASK-002"
  - id: "TASK-002"
    name: "Second Task"
    prompt: "Do second thing"
    expected_deliverable: "Second thing done"
    dependencies:
      - "TASK-001"
"""

    with pytest.raises(TaskLoadError, match="Circular dependency"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_nonexistent_dependency():
    """Test that nonexistent dependencies are detected."""
    yaml_content = """
tasks:
  - id: "TASK-001"
    name: "Task"
    prompt: "Do thing"
    expected_deliverable: "Thing done"
    dependencies:
      - "NONEXISTENT"
"""

    with pytest.raises(TaskLoadError, match="non-existent"):
        TaskLoader.load_from_yaml_string(yaml_content)


def test_get_runnable_tasks():
    """Test getting runnable tasks (no pending dependencies)."""
    yaml_content = """
tasks:
  - id: "BASE-001"
    name: "Base Task"
    prompt: "Do base thing"
    expected_deliverable: "Base thing done"
  - id: "DEPENDENT-001"
    name: "Dependent Task"
    prompt: "Do dependent thing"
    expected_deliverable: "Dependent thing done"
    dependencies:
      - "BASE-001"
  - id: "INDEPENDENT-001"
    name: "Independent Task"
    prompt: "Do independent thing"
    expected_deliverable: "Independent thing done"
"""

    task_list = TaskLoader.load_from_yaml_string(yaml_content)

    # Initially, only tasks without dependencies are runnable
    runnable = task_list.get_runnable_tasks()
    runnable_ids = [t.id for t in runnable]
    assert "BASE-001" in runnable_ids
    assert "INDEPENDENT-001" in runnable_ids
    assert "DEPENDENT-001" not in runnable_ids

    # After completing BASE-001, DEPENDENT-001 becomes runnable
    base_task = task_list.get_task("BASE-001")
    base_task.complete()

    runnable = task_list.get_runnable_tasks()
    runnable_ids = [t.id for t in runnable]
    assert "DEPENDENT-001" in runnable_ids
