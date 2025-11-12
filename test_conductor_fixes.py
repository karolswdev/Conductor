#!/usr/bin/env python3
"""
Test script to validate Conductor fixes for accessibility snapshot implementation.

This script tests the key components we've fixed:
1. BrowserController snapshot-based interactions
2. Orchestrator task execution
3. Repository selection
4. Completion detection
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from conductor.mcp.browser import BrowserController
from conductor.mcp.client import MCPClient
from conductor.utils.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


# Sample accessibility snapshot (simplified version) - These need to be parsed dictionaries
import yaml

def parse_snapshot(snapshot_str):
    """Parse YAML snapshot to dict."""
    return yaml.safe_load(snapshot_str)

SAMPLE_SNAPSHOT = parse_snapshot("""
page:
  title: Claude Code
  url: https://claude.ai/code
  content:
    - type: textbox
      name: "Find a small todo in the codebase and do it"
      ref: e1018
      placeholder: "Find a small todo in the codebase and do it"
    - type: button
      name: "Select repository"
      ref: e1020
      text: "Select repository"
    - type: button
      name: "Submit"
      ref: e1022
      disabled: false
    - type: button
      name: "Sonnet 4.5"
      ref: e1024
""")

SAMPLE_SNAPSHOT_WITH_REPO_DROPDOWN = parse_snapshot("""
page:
  title: Claude Code
  url: https://claude.ai/code
  content:
    - type: menu
      ref: m100
      items:
        - type: menuitem
          name: "Conductor karolswdev"
          ref: m101
          text: "Conductor karolswdev"
        - type: menuitem
          name: "web-based-researcher karolswdev"
          ref: m102
          text: "web-based-researcher karolswdev"
""")

SAMPLE_SNAPSHOT_TASK_RUNNING_STR = """
page:
  title: Claude Code
  url: https://claude.ai/code/session_011CV4beKrFjCAcPw3r7tC3u
  content:
    - type: text
      content: "Thinking..."
    - type: button
      name: "Create PR"
      ref: e2000
      disabled: true
      text: "Create PR"
    - type: text
      content: "Working on: claude/test-conductor-011CV4beKrFjCAcPw3r7tC3u"
"""

SAMPLE_SNAPSHOT_TASK_COMPLETE_STR = """
page:
  title: Claude Code
  url: https://claude.ai/code/session_011CV4beKrFjCAcPw3r7tC3u
  content:
    - type: button
      name: "Create PR"
      ref: e2000
      text: "Create PR"
    - type: text
      content: "Branch: claude/test-conductor-011CV4beKrFjCAcPw3r7tC3u"
    - type: text
      content: "Task completed successfully"
"""

SAMPLE_SNAPSHOT_TASK_RUNNING = parse_snapshot(SAMPLE_SNAPSHOT_TASK_RUNNING_STR)
SAMPLE_SNAPSHOT_TASK_COMPLETE = parse_snapshot(SAMPLE_SNAPSHOT_TASK_COMPLETE_STR)


class TestBrowserController:
    """Test the BrowserController fixes."""

    def __init__(self):
        self.mock_client = AsyncMock(spec=MCPClient)
        self.browser = BrowserController(self.mock_client)
        # Patch the get_snapshot method to return our mock data
        self.browser.get_snapshot = AsyncMock()

    async def test_click_with_snapshot(self):
        """Test that click properly uses snapshots."""
        print("\n=== Testing Click with Snapshot ===")

        # Setup mock to return snapshot
        self.browser.get_snapshot.return_value = SAMPLE_SNAPSHOT
        self.mock_client.call_tool.return_value = None  # Click result

        # Test clicking submit button
        await self.browser.click("Submit button")

        # Verify it called snapshot first
        self.browser.get_snapshot.assert_called_once()

        # Verify it called click with correct parameters
        self.mock_client.call_tool.assert_called_once_with(
            "browser_click",
            {"element": "Submit button", "ref": "e1022"}
        )

        print("✓ Click properly retrieves snapshot and uses ref")

    async def test_fill_with_snapshot(self):
        """Test that fill properly uses snapshots."""
        print("\n=== Testing Fill with Snapshot ===")

        # Reset mocks
        self.mock_client.reset_mock()
        self.browser.get_snapshot.reset_mock()
        self.browser.get_snapshot.return_value = SAMPLE_SNAPSHOT
        self.mock_client.call_tool.return_value = None  # Type result

        # Test filling text
        await self.browser.fill("Message input textbox", "Test task prompt")

        # Verify it called snapshot first
        self.browser.get_snapshot.assert_called_once()

        # Verify it called type with correct parameters
        self.mock_client.call_tool.assert_called_once_with(
            "browser_type",
            {
                "element": "Message input textbox",
                "ref": "e1018",
                "text": "Test task prompt",
                "submit": False
            }
        )

        print("✓ Fill properly retrieves snapshot and uses ref")

    async def test_completion_detection(self):
        """Test Create PR button completion detection."""
        print("\n=== Testing Completion Detection ===")

        # Test with disabled button (task running) - pass as string since the method expects string
        result = self.browser.is_create_pr_button_enabled(SAMPLE_SNAPSHOT_TASK_RUNNING_STR)
        assert result == False, "Should detect disabled Create PR button"
        print("✓ Correctly detects disabled Create PR button")

        # Test with enabled button (task complete) - pass as string
        result = self.browser.is_create_pr_button_enabled(SAMPLE_SNAPSHOT_TASK_COMPLETE_STR)
        assert result == True, "Should detect enabled Create PR button"
        print("✓ Correctly detects enabled Create PR button")

    async def test_branch_extraction(self):
        """Test branch name extraction."""
        print("\n=== Testing Branch Extraction ===")

        branch = self.browser.extract_branch_name(SAMPLE_SNAPSHOT_TASK_COMPLETE_STR)
        assert branch == "claude/test-conductor-011CV4beKrFjCAcPw3r7tC3u"
        print(f"✓ Extracted branch name: {branch}")

    async def test_repository_selection(self):
        """Test repository selection workflow."""
        print("\n=== Testing Repository Selection ===")

        # Mock sequence
        self.mock_client.reset_mock()
        self.browser.get_snapshot.reset_mock()

        # Set up return values for each call
        self.browser.get_snapshot.side_effect = [
            SAMPLE_SNAPSHOT,  # First click
            SAMPLE_SNAPSHOT_WITH_REPO_DROPDOWN,  # Second click
        ]
        self.mock_client.call_tool.return_value = None  # Click results

        # Simulate repository selection
        await self.browser.click("Select repository button")
        await asyncio.sleep(0.1)  # Simulate wait
        await self.browser.click("Conductor karolswdev repository option")

        # Verify two snapshots were retrieved
        assert self.browser.get_snapshot.call_count == 2

        # Verify the click calls
        calls = self.mock_client.call_tool.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "browser_click"
        assert calls[0][0][1]["ref"] == "e1020"  # Select repository button
        assert calls[1][0][0] == "browser_click"
        assert calls[1][0][1]["ref"] == "m101"  # Repository menu item

        print("✓ Repository selection workflow works correctly")

    async def run_all_tests(self):
        """Run all browser controller tests."""
        await self.test_click_with_snapshot()
        await self.test_fill_with_snapshot()
        await self.test_completion_detection()
        await self.test_branch_extraction()
        await self.test_repository_selection()
        print("\n✅ All BrowserController tests passed!")


class TestOrchestratorIntegration:
    """Test the orchestrator integration."""

    async def test_task_execution_flow(self):
        """Test the complete task execution flow."""
        print("\n=== Testing Orchestrator Task Execution Flow ===")

        from conductor.orchestrator import Orchestrator
        from conductor.tasks.models import TaskList, Task

        # Create mock config and task
        config = MagicMock()
        config.mcp = MagicMock()
        config.mcp.server_url = "ws://localhost:3000"
        config.mcp.timeout = 60
        config.mcp.max_retries = 3
        config.auth = MagicMock()
        config.auth.timeout = 300
        config.auth.check_interval = 5
        config.auth.headless = False

        task = Task(
            id="test-task-001",
            name="Test Task",
            prompt="Fix a small bug",
            repository="karolswdev/Conductor",
            timeout=600,
            expected_deliverable="Bug fix completed"
        )
        task_list = TaskList(tasks=[task])

        orchestrator = Orchestrator(config, task_list)

        # Mock the browser and client
        orchestrator.mcp_client = AsyncMock()
        orchestrator.browser = AsyncMock(spec=BrowserController)

        # Mock browser methods
        orchestrator.browser.create_tab = AsyncMock(return_value=0)
        orchestrator.browser.switch_tab = AsyncMock()
        orchestrator.browser.navigate = AsyncMock()
        orchestrator.browser.click = AsyncMock()
        orchestrator.browser.fill = AsyncMock()
        orchestrator.browser.get_current_url = AsyncMock(
            return_value="https://claude.ai/code/session_011CV4beKrFjCAcPw3r7tC3u"
        )
        orchestrator.browser.dismiss_notification_dialog = AsyncMock()
        orchestrator.browser.get_text = AsyncMock(return_value=SAMPLE_SNAPSHOT_TASK_COMPLETE_STR)
        orchestrator.browser.client = AsyncMock()
        orchestrator.browser.client.call_tool = AsyncMock(
            return_value={"content": SAMPLE_SNAPSHOT_TASK_COMPLETE_STR}
        )

        # Test execution
        await orchestrator._execute_task(task)

        # Verify key interactions
        orchestrator.browser.create_tab.assert_called_once()
        orchestrator.browser.navigate.assert_called_with("https://claude.ai/code")

        # Verify repository selection
        assert any(
            "Select repository" in str(call)
            for call in orchestrator.browser.click.call_args_list
        ), "Should click repository selector"

        # Verify prompt submission
        orchestrator.browser.fill.assert_called_with("Message input textbox", "Fix a small bug")
        assert any(
            "Submit" in str(call)
            for call in orchestrator.browser.click.call_args_list
        ), "Should click submit button"

        # Verify task marked as complete
        assert task.status.value == "completed"
        assert task.session_id == "session_011CV4beKrFjCAcPw3r7tC3u"

        print("✓ Task execution flow works correctly")
        print(f"✓ Session ID extracted: {task.session_id}")
        print(f"✓ Task status: {task.status.value}")


async def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing Conductor Fixes")
    print("=" * 50)

    # Test BrowserController
    browser_tests = TestBrowserController()
    await browser_tests.run_all_tests()

    # Test Orchestrator Integration
    orchestrator_tests = TestOrchestratorIntegration()
    await orchestrator_tests.test_task_execution_flow()

    print("\n" + "=" * 50)
    print("✅ All tests passed successfully!")
    print("=" * 50)
    print("\nThe implementation is ready for integration testing with the real Claude Code interface.")
    print("\nNext steps:")
    print("1. Run 'conductor doctor' to verify MCP connection")
    print("2. Test with a simple task using 'conductor run todo/01-simple-test.yaml'")
    print("3. Monitor logs for any issues with snapshot parsing")
    print("4. Verify branch creation and session management")


if __name__ == "__main__":
    asyncio.run(main())