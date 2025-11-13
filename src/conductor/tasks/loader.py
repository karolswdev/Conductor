"""
Task loader for loading tasks from YAML files.
"""

import re
import yaml
from pathlib import Path
from typing import Union, Dict, Any
from pydantic import ValidationError

from .models import Task, TaskList, RetryPolicy


class TaskLoadError(Exception):
    """Exception raised when task loading fails."""

    pass


class TaskLoader:
    """
    Loads and validates tasks from YAML files.

    Example YAML format:
    ```yaml
    tasks:
      - id: "AUTH-001"
        name: "Add Auth Tests"
        prompt: "Create unit tests for authentication"
        expected_deliverable: "test_auth.py with full coverage"
        priority: high
        dependencies: []
        repository: "karolswdev/my-project"
    ```
    """

    @staticmethod
    def load_from_file(file_path: Union[str, Path]) -> TaskList:
        """
        Load tasks from a YAML file.

        Args:
            file_path: Path to the YAML file

        Returns:
            TaskList containing validated tasks

        Raises:
            TaskLoadError: If file cannot be read or validation fails
        """
        path = Path(file_path)

        if not path.exists():
            raise TaskLoadError(f"Task file not found: {path}")

        if not path.is_file():
            raise TaskLoadError(f"Path is not a file: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise TaskLoadError(f"Invalid YAML syntax: {e}") from e
        except Exception as e:
            raise TaskLoadError(f"Failed to read file: {e}") from e

        return TaskLoader.load_from_dict(data)

    @staticmethod
    def load_from_dict(data: Dict[str, Any]) -> TaskList:
        """
        Load tasks from a dictionary.

        Args:
            data: Dictionary containing task definitions

        Returns:
            TaskList containing validated tasks

        Raises:
            TaskLoadError: If validation fails
        """
        if not isinstance(data, dict):
            raise TaskLoadError("YAML must contain a dictionary at root level")

        if "tasks" not in data:
            raise TaskLoadError("YAML must contain a 'tasks' key")

        tasks_data = data["tasks"]

        # Pull defaults from config section if present
        default_repo = None
        config_block = data.get("config")
        if isinstance(config_block, dict):
            default_repo = config_block.get("default_repository")
            if default_repo:
                if not re.match(r"^[\w-]+/[\w-]+$", default_repo):
                    raise TaskLoadError(
                        f"config.default_repository must be in owner/repo format, got: {default_repo}"
                    )

        if not isinstance(tasks_data, list):
            raise TaskLoadError("'tasks' must be a list")

        if not tasks_data:
            raise TaskLoadError("Task list is empty")

        # Parse each task
        tasks = []
        for i, task_data in enumerate(tasks_data):
            if not isinstance(task_data, dict):
                raise TaskLoadError(f"Task at index {i} must be a dictionary")

            try:
                # Apply defaults
                if default_repo and not task_data.get("repository"):
                    task_data["repository"] = default_repo

                # Handle retry_policy if present
                if "retry_policy" in task_data and isinstance(task_data["retry_policy"], dict):
                    task_data["retry_policy"] = RetryPolicy(**task_data["retry_policy"])

                task = Task(**task_data)
                tasks.append(task)
            except ValidationError as e:
                error_msgs = []
                for error in e.errors():
                    field = ".".join(str(loc) for loc in error["loc"])
                    msg = error["msg"]
                    error_msgs.append(f"  - {field}: {msg}")

                raise TaskLoadError(
                    f"Validation failed for task at index {i} (id: {task_data.get('id', 'unknown')}):\n"
                    + "\n".join(error_msgs)
                ) from e

        # Create and validate task list (checks for unique IDs and circular dependencies)
        try:
            task_list = TaskList(tasks=tasks)
        except ValidationError as e:
            error_msgs = []
            for error in e.errors():
                error_msgs.append(f"  - {error['msg']}")
            raise TaskLoadError("Task list validation failed:\n" + "\n".join(error_msgs)) from e

        return task_list

    @staticmethod
    def load_from_yaml_string(yaml_string: str) -> TaskList:
        """
        Load tasks from a YAML string.

        Args:
            yaml_string: YAML content as string

        Returns:
            TaskList containing validated tasks

        Raises:
            TaskLoadError: If validation fails
        """
        try:
            data = yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            raise TaskLoadError(f"Invalid YAML syntax: {e}") from e

        return TaskLoader.load_from_dict(data)

    @staticmethod
    def validate_file(file_path: Union[str, Path]) -> tuple[bool, str]:
        """
        Validate a task file without loading it.

        Args:
            file_path: Path to the YAML file

        Returns:
            Tuple of (is_valid, error_message)
            If valid, error_message is an empty string
        """
        try:
            TaskLoader.load_from_file(file_path)
            return True, ""
        except TaskLoadError as e:
            return False, str(e)

    @staticmethod
    def get_task_summary(file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Get a summary of tasks in a file without full validation.

        Args:
            file_path: Path to the YAML file

        Returns:
            Dictionary with task counts and basic info
        """
        try:
            task_list = TaskLoader.load_from_file(file_path)
            return {
                "total_tasks": len(task_list),
                "task_ids": [task.id for task in task_list.tasks],
                "priorities": {
                    "high": sum(1 for t in task_list.tasks if t.priority.value == "high"),
                    "medium": sum(1 for t in task_list.tasks if t.priority.value == "medium"),
                    "low": sum(1 for t in task_list.tasks if t.priority.value == "low"),
                },
                "has_dependencies": any(task.dependencies for task in task_list.tasks),
            }
        except TaskLoadError as e:
            return {"error": str(e)}
