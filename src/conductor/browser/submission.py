"""
Task submission to Claude Code.
Implements Story 4.2: Task Submission
"""

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass

from ..mcp.browser import BrowserController, MCPError
from ..tasks.models import Task


logger = logging.getLogger(__name__)


@dataclass
class SubmissionResult:
    """Result of task submission."""

    success: bool
    session_id: Optional[str] = None
    branch_name: Optional[str] = None
    error_message: Optional[str] = None


class TaskSubmitter:
    """
    Handles submission of tasks to Claude Code.

    This implements Story 4.2: Task Submission
    - Navigate to correct repository
    - Enter task prompt in input field
    - Click submit button
    - Verify task started processing
    - Handle submission failures
    """

    # Selectors for Claude Code UI elements
    # These will need to be discovered/updated based on actual UI
    SELECTORS = {
        "input_field": "textarea[placeholder*='message']",
        "submit_button": "button[type='submit']",
        "session_indicator": "[data-testid='session-active']",
        "repository_selector": "[data-testid='repository-select']",
        "repository_input": "input[placeholder*='repository']",
    }

    def __init__(self, browser: BrowserController, repository: Optional[str] = None):
        """
        Initialize task submitter.

        Args:
            browser: Browser controller instance
            repository: Default repository (owner/repo format)
        """
        self.browser = browser
        self.default_repository = repository

    async def submit_task(
        self,
        task: Task,
        repository: Optional[str] = None,
        timeout: float = 60.0,
    ) -> SubmissionResult:
        """
        Submit a task to Claude Code.

        Args:
            task: Task to submit
            repository: Repository to use (overrides default)
            timeout: Maximum time to wait for submission

        Returns:
            SubmissionResult with success status and session info
        """
        repo = repository or task.repository or self.default_repository

        if not repo:
            return SubmissionResult(
                success=False, error_message="No repository specified"
            )

        try:
            logger.info(f"Submitting task {task.id} to repository {repo}")

            # Step 1: Navigate to repository (if needed)
            await self._ensure_repository(repo, timeout)

            # Step 2: Enter the task prompt
            await self._enter_prompt(task, timeout)

            # Step 3: Submit the task
            await self._click_submit(timeout)

            # Step 4: Verify task started
            session_info = await self._verify_submission(timeout)

            if session_info:
                logger.info(
                    f"Task {task.id} submitted successfully. Session: {session_info['session_id']}"
                )
                return SubmissionResult(
                    success=True,
                    session_id=session_info.get("session_id"),
                    branch_name=session_info.get("branch_name"),
                )
            else:
                return SubmissionResult(
                    success=False,
                    error_message="Failed to verify task submission",
                )

        except MCPError as e:
            logger.error(f"Task submission failed: {e}")
            return SubmissionResult(success=False, error_message=str(e))

        except Exception as e:
            logger.error(f"Unexpected error during task submission: {e}")
            return SubmissionResult(
                success=False, error_message=f"Unexpected error: {str(e)}"
            )

    async def _ensure_repository(self, repository: str, timeout: float) -> None:
        """
        Ensure we're working in the correct repository.

        Args:
            repository: Repository name (owner/repo)
            timeout: Maximum time to wait
        """
        try:
            # Check if repository selector exists
            repo_selector_exists = await self.browser.wait_for_selector(
                self.SELECTORS["repository_selector"],
                timeout=5.0,
                state="visible",
            )

            if repo_selector_exists:
                # Click repository selector
                await self.browser.click(
                    self.SELECTORS["repository_selector"], timeout=timeout
                )

                # Wait for input to appear
                await self.browser.wait_for_selector(
                    self.SELECTORS["repository_input"],
                    timeout=timeout,
                    state="visible",
                )

                # Enter repository name
                await self.browser.fill(
                    self.SELECTORS["repository_input"], repository, timeout=timeout
                )

                # Press Enter to select
                # TODO: This might need to be adjusted based on actual UI
                await asyncio.sleep(0.5)

                logger.info(f"Repository set to: {repository}")

        except MCPError as e:
            logger.warning(f"Could not set repository: {e}")
            # Continue anyway - repository might already be set

    async def _enter_prompt(self, task: Task, timeout: float) -> None:
        """
        Enter the task prompt into the input field.

        Args:
            task: Task containing the prompt
            timeout: Maximum time to wait
        """
        # Wait for input field to be available
        input_found = await self.browser.wait_for_selector(
            self.SELECTORS["input_field"],
            timeout=timeout,
            state="visible",
        )

        if not input_found:
            raise MCPError("Input field not found")

        # Build the full prompt with context
        full_prompt = self._build_prompt(task)

        # Enter the prompt
        await self.browser.fill(
            self.SELECTORS["input_field"], full_prompt, timeout=timeout
        )

        logger.info(f"Entered prompt for task {task.id}")

    def _build_prompt(self, task: Task) -> str:
        """
        Build the full prompt with task context.

        Args:
            task: Task to build prompt for

        Returns:
            Complete prompt string
        """
        prompt_parts = []

        # Add task identifier
        prompt_parts.append(f"[Task ID: {task.id}]")

        # Add main prompt
        prompt_parts.append(task.prompt)

        # Add expected deliverable
        prompt_parts.append(f"\nExpected Deliverable: {task.expected_deliverable}")

        # Add priority if high
        if task.priority.value == "high":
            prompt_parts.append("\nPriority: HIGH - Please prioritize this task.")

        return "\n\n".join(prompt_parts)

    async def _click_submit(self, timeout: float) -> None:
        """
        Click the submit button.

        Args:
            timeout: Maximum time to wait
        """
        # Wait for submit button to be enabled
        button_found = await self.browser.wait_for_selector(
            self.SELECTORS["submit_button"],
            timeout=timeout,
            state="visible",
        )

        if not button_found:
            raise MCPError("Submit button not found")

        # Click the submit button
        await self.browser.click(self.SELECTORS["submit_button"], timeout=timeout)

        logger.info("Clicked submit button")

        # Brief pause for submission to process
        await asyncio.sleep(1.0)

    async def _verify_submission(self, timeout: float) -> Optional[dict]:
        """
        Verify that the task was submitted successfully.

        Args:
            timeout: Maximum time to wait

        Returns:
            Dictionary with session info, or None if verification failed
        """
        # Wait for session indicator to appear
        session_active = await self.browser.wait_for_selector(
            self.SELECTORS["session_indicator"],
            timeout=timeout,
            state="visible",
        )

        if not session_active:
            logger.warning("Session indicator not found")
            return None

        # Try to extract session ID from URL
        try:
            current_url = await self.browser.get_current_url()

            # Extract session ID from URL (format: claude.ai/code/session_XXXXX)
            if "/code/" in current_url:
                session_id = current_url.split("/code/")[1].split("?")[0]

                # Try to extract branch name (might be in URL or page)
                # This is a simplified version - actual implementation may vary
                branch_name = f"claude/task-{session_id[:8]}"

                return {
                    "session_id": session_id,
                    "branch_name": branch_name,
                    "url": current_url,
                }

        except Exception as e:
            logger.warning(f"Could not extract session info: {e}")

        return None

    async def wait_for_task_completion(
        self,
        session_id: str,
        timeout: float = 3600.0,
        check_interval: float = 10.0,
    ) -> bool:
        """
        Wait for a task to complete.

        Args:
            session_id: Session ID to monitor
            timeout: Maximum time to wait
            check_interval: How often to check status

        Returns:
            True if task completed, False if timeout
        """
        # This is a placeholder for future implementation
        # Would monitor the session for completion indicators

        logger.info(f"Waiting for task completion (session: {session_id})")

        # For now, just wait a fixed amount
        await asyncio.sleep(min(timeout, 60.0))

        return True

    async def check_for_pr_button(self) -> bool:
        """
        Check if PR creation button is available.

        Returns:
            True if PR button found, False otherwise
        """
        # Common PR button selectors
        pr_button_selectors = [
            "button:has-text('Create Pull Request')",
            "button:has-text('Create PR')",
            "[data-testid='create-pr-button']",
        ]

        for selector in pr_button_selectors:
            try:
                found = await self.browser.wait_for_selector(
                    selector, timeout=2.0, state="visible"
                )
                if found:
                    logger.info(f"PR button found: {selector}")
                    return True
            except:
                continue

        return False

    async def create_pr(self, timeout: float = 30.0) -> Optional[str]:
        """
        Create a pull request for the current session.

        Args:
            timeout: Maximum time to wait

        Returns:
            PR URL if successful, None otherwise
        """
        try:
            # Check for PR button
            has_button = await self.check_for_pr_button()

            if not has_button:
                logger.warning("PR button not found")
                return None

            # Click PR button
            pr_button_selectors = [
                "button:has-text('Create Pull Request')",
                "button:has-text('Create PR')",
            ]

            for selector in pr_button_selectors:
                try:
                    await self.browser.click(selector, timeout=5.0)
                    logger.info("Clicked PR button")
                    break
                except:
                    continue

            # Wait for PR to be created
            await asyncio.sleep(2.0)

            # Try to extract PR URL
            current_url = await self.browser.get_current_url()

            # If URL changed to a PR page, return it
            if "/pull/" in current_url:
                logger.info(f"PR created: {current_url}")
                return current_url

            # Otherwise, try to find PR link in page
            # This would require additional selectors

            return None

        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            return None
