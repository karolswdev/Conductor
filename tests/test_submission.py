"""
Tests for task submission functionality.
"""

import pytest
from conductor.browser.submission import TaskSubmitter, SubmissionResult
from conductor.tasks.models import Task, Priority
from conductor.mcp.browser import BrowserController
from conductor.mcp.client import MCPClient


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="TEST-001",
        name="Test Task",
        prompt="This is a test task prompt",
        expected_deliverable="test_output.txt",
        priority=Priority.HIGH,
    )


@pytest.fixture
async def mock_browser():
    """Create a mock browser controller."""
    client = MCPClient()
    browser = BrowserController(client)
    return browser


@pytest.mark.asyncio
async def test_build_prompt(sample_task):
    """Test prompt building with task context."""
    submitter = TaskSubmitter(None, repository="test/repo")

    prompt = submitter._build_prompt(sample_task)

    assert "[Task ID: TEST-001]" in prompt
    assert sample_task.prompt in prompt
    assert sample_task.expected_deliverable in prompt
    assert "Priority: HIGH" in prompt


@pytest.mark.asyncio
async def test_build_prompt_medium_priority():
    """Test that medium priority doesn't add priority note."""
    task = Task(
        id="TEST-002",
        name="Medium Task",
        prompt="Test prompt",
        expected_deliverable="output.txt",
        priority=Priority.MEDIUM,
    )

    submitter = TaskSubmitter(None)
    prompt = submitter._build_prompt(task)

    assert "Priority: HIGH" not in prompt


def test_submission_result_success():
    """Test successful submission result."""
    result = SubmissionResult(
        success=True,
        session_id="session_123",
        branch_name="claude/test-branch",
    )

    assert result.success is True
    assert result.session_id == "session_123"
    assert result.branch_name == "claude/test-branch"
    assert result.error_message is None


def test_submission_result_failure():
    """Test failed submission result."""
    result = SubmissionResult(success=False, error_message="Connection failed")

    assert result.success is False
    assert result.session_id is None
    assert result.error_message == "Connection failed"
