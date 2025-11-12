"""
TUI-based orchestrator for task execution.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime
from textual import work

from conductor.mcp.client import MCPClient
from conductor.mcp.browser import BrowserController
from conductor.browser.auth import AuthenticationFlow, AuthStatus
from conductor.browser.session import SessionManager
from conductor.tasks.models import TaskList, Task, TaskStatus
from conductor.utils.config import Config
from conductor.utils.retry import retry_async, exponential_backoff
from conductor.tui.app import ConductorTUI


logger = logging.getLogger(__name__)


class TUIOrchestrator:
    """
    Orchestrates task execution with TUI interface.

    Integrates the Textual TUI with the orchestration logic.
    """

    def __init__(self, config: Config, task_list: TaskList, app: ConductorTUI):
        """
        Initialize TUI orchestrator.

        Args:
            config: Configuration
            task_list: List of tasks to execute
            app: TUI application instance
        """
        self.config = config
        self.task_list = task_list
        self.app = app
        self.mcp_client: Optional[MCPClient] = None
        self.browser: Optional[BrowserController] = None
        self.auth_flow: Optional[AuthenticationFlow] = None
        self.session_manager = SessionManager()
        self.start_time = datetime.now()

    async def run(self) -> None:
        """Run the orchestration flow with TUI updates."""
        try:
            self.app.notify("Starting Conductor Orchestrator", title="🎭 Conductor")

            # Step 1: Initialize MCP connection (skip if already initialized)
            if not self.mcp_client:
                await self._initialize_mcp()

            # Step 2: Authenticate (skip if already authenticated)
            if not self.auth_flow:
                await self._authenticate()
            else:
                self.app.notify("Already authenticated!", title="Auth", severity="information")

            # Step 3: Execute tasks
            await self._execute_tasks()

            # Step 4: Show completion
            self._show_completion()

        except KeyboardInterrupt:
            self.app.notify("Interrupted by user", title="Warning", severity="warning")

        except Exception as e:
            logger.exception("Orchestration failed")
            self.app.notify(
                f"Error: {str(e)}", title="Orchestration Failed", severity="error"
            )

        finally:
            await self._cleanup()

    async def _initialize_mcp(self) -> None:
        """Initialize MCP connection."""
        self.app.notify("Initializing MCP connection...", title="MCP")

        self.mcp_client = MCPClient(
            server_url=self.config.mcp.server_url,
            timeout=self.config.mcp.timeout,
            max_retries=self.config.mcp.max_retries,
        )

        await self.mcp_client.connect()

        self.browser = BrowserController(self.mcp_client)

        self.app.notify("MCP connected successfully", title="MCP", severity="information")

    async def _authenticate(self) -> None:
        """Run authentication flow."""
        self.app.notify(
            "Browser opening - log in to Claude Code, then press Enter in terminal",
            title="Authentication",
            timeout=10,
        )

        self.auth_flow = AuthenticationFlow(
            browser=self.browser,
            timeout=self.config.auth.timeout,
            check_interval=self.config.auth.check_interval,
        )

        status = await self.auth_flow.start(
            headless=self.config.auth.headless,
            wait_for_user_input=True
        )

        if status == AuthStatus.AUTHENTICATED:
            self.app.notify(
                "Authentication successful!", title="Auth", severity="information"
            )
        elif status == AuthStatus.TIMEOUT:
            self.app.notify(
                "Authentication timed out", title="Auth", severity="error"
            )
            raise RuntimeError("Authentication timeout")
        else:
            self.app.notify(
                f"Authentication failed: {status}", title="Auth", severity="error"
            )
            raise RuntimeError(f"Authentication failed: {status}")

    async def _execute_tasks(self) -> None:
        """Execute all tasks with TUI updates."""
        self.app.notify(
            f"Executing {len(self.task_list)} tasks", title="Execution"
        )

        for task in self.task_list.tasks:
            # Update task queue display
            self.app.update_task_queue(current_task_id=task.id)

            # Check if dependencies are met
            if not self._dependencies_met(task):
                self.app.notify(
                    f"Skipping {task.id}: dependencies not met",
                    title="Task Skipped",
                    severity="warning",
                )
                task.skip()
                self.app.update_task_queue()
                continue

            # Execute task with retries
            task_start = datetime.now()

            try:
                await self._execute_task_with_retry(task, task_start)
                self.app.notify(
                    f"Task {task.id} completed successfully",
                    title="Success",
                    severity="information",
                )

            except Exception as e:
                logger.error(f"Task {task.id} failed: {e}")
                self.app.notify(
                    f"Task {task.id} failed: {str(e)}",
                    title="Task Failed",
                    severity="error",
                )
                task.fail(str(e))

            # Update displays
            self.app.update_task_queue()
            self.app.update_metrics()

        self.app.notify("All tasks processed!", title="Complete", severity="information")

    def _dependencies_met(self, task: Task) -> bool:
        """Check if task dependencies are met."""
        for dep_id in task.dependencies:
            dep_task = self.task_list.get_task(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    async def _execute_task_with_retry(self, task: Task, start_time: datetime) -> None:
        """
        Execute a single task with retry logic.

        Args:
            task: Task to execute
            start_time: When task execution started
        """
        task.start()

        for attempt in range(task.retry_policy.max_attempts):
            try:
                # Update execution panel
                elapsed = (datetime.now() - start_time).total_seconds()
                self.app.update_execution(
                    task=task,
                    progress=0.0,
                    elapsed=elapsed,
                    retries=attempt,
                )

                # Execute the task
                await self._execute_single_task(task, start_time)

                # Success!
                return

            except Exception as e:
                logger.warning(f"Task {task.id} attempt {attempt + 1} failed: {e}")
                task.increment_retry()

                if attempt < task.retry_policy.max_attempts - 1:
                    # Calculate backoff delay
                    delay = exponential_backoff(
                        attempt=attempt,
                        initial_delay=task.retry_policy.initial_delay,
                        backoff_factor=task.retry_policy.backoff_factor,
                        max_delay=task.retry_policy.max_delay,
                        jitter=task.retry_policy.jitter,
                    )

                    self.app.notify(
                        f"Retrying in {delay:.1f}s... (attempt {attempt + 2}/{task.retry_policy.max_attempts})",
                        title=f"Retry: {task.id}",
                        timeout=5,
                    )

                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    raise

    async def _execute_single_task(self, task: Task, start_time: datetime) -> None:
        """
        Execute a single task attempt in its own browser tab.

        Args:
            task: Task to execute
            start_time: When execution started
        """
        tab_index = None

        try:
            # Step 1: Create a new tab for this task AND navigate to Claude Code atomically
            logger.info(f"Creating new tab with Claude Code URL for task {task.id}")
            tab_index = await self.browser.create_tab(url="https://claude.ai/code")
            await self.browser.switch_tab(tab_index)

            # Wait for page to load
            await asyncio.sleep(3.0)

            self.app.update_execution(
                task=task,
                progress=0.2,
                elapsed=(datetime.now() - start_time).total_seconds(),
                retries=task.retry_count,
            )

            # Step 2: Select repository if specified
            if hasattr(task, 'repository') and task.repository:
                try:
                    logger.info(f"Selecting repository: {task.repository}")
                    await self.browser.click("Select repository button")
                    await asyncio.sleep(2.0)

                    parts = task.repository.split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        repo_name = parts[1]
                        await self.browser.click(f"{repo_name} {owner} repository option")
                    else:
                        await self.browser.click(f"{task.repository} repository option")

                    await asyncio.sleep(1.0)
                except Exception as e:
                    logger.warning(f"Could not select repository: {e}")

            self.app.update_execution(
                task=task,
                progress=0.3,
                elapsed=(datetime.now() - start_time).total_seconds(),
                retries=task.retry_count,
            )

            # Step 3: Submit task prompt
            logger.info(f"Submitting task prompt for task {task.id}")
            try:
                await self.browser.fill("Message input textbox", task.prompt)
                await asyncio.sleep(1.0)
                await self.browser.click("Submit button")
            except Exception as e:
                logger.warning(f"Could not submit prompt automatically: {e}")
                raise

            # Step 4: Wait for session URL to update
            await asyncio.sleep(3.0)
            current_url = await self.browser.get_current_url()
            session_id = self._extract_session_id_from_url(current_url)

            # Dismiss notification dialog if present
            await self.browser.dismiss_notification_dialog()

            self.app.update_execution(
                task=task,
                progress=0.4,
                elapsed=(datetime.now() - start_time).total_seconds(),
                retries=task.retry_count,
            )

            # Step 5: Monitor for completion
            logger.info(f"Waiting for task {task.id} to complete...")
            await self._wait_for_task_completion(task, tab_index, start_time)

            self.app.update_execution(
                task=task,
                progress=0.9,
                elapsed=(datetime.now() - start_time).total_seconds(),
                retries=task.retry_count,
            )

            # Step 6: Extract branch name
            branch_name = f"claude/{task.id.lower()}"
            try:
                page_text = await self.browser.get_text("body")
                extracted_branch = self._extract_branch_name_from_page(page_text)
                if extracted_branch:
                    branch_name = extracted_branch
            except Exception as e:
                logger.debug(f"Could not extract branch name: {e}")

            # Step 7: Record session
            final_url = await self.browser.get_current_url()
            self.session_manager.add_session(
                session_id=session_id or f"session_{task.id}_{int(datetime.now().timestamp())}",
                task_id=task.id,
                branch_name=branch_name,
                url=final_url,
            )

            # Update browser preview
            self.app.update_browser(
                url=final_url,
                branch=branch_name,
                preview=f"Task {task.id} completed",
            )

            self.app.update_execution(
                task=task,
                progress=1.0,
                elapsed=(datetime.now() - start_time).total_seconds(),
                retries=task.retry_count,
            )

            task.complete(
                session_id=session_id or f"session_{task.id}",
                branch_name=branch_name,
            )

        except Exception as e:
            logger.error(f"Task {task.id} execution failed: {e}")
            raise

    def _extract_session_id_from_url(self, url: str) -> Optional[str]:
        """Extract session ID from Claude Code URL."""
        if "/code/" in url:
            parts = url.split("/code/")
            if len(parts) > 1:
                session_id = parts[1].split("?")[0].split("#")[0]
                return session_id if session_id else None
        return None

    def _extract_branch_name_from_page(self, page_text: str) -> Optional[str]:
        """Extract git branch name from page content."""
        import re

        patterns = [
            r"branch[:\s]+([a-zA-Z0-9/_-]+)",
            r"claude/([a-zA-Z0-9/_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return match.group(1) if "claude/" in pattern else f"claude/{match.group(1)}"

        return None

    async def _wait_for_task_completion(
        self,
        task: Task,
        tab_index: int,
        start_time: datetime,
        timeout: int = 600,
        check_interval: float = 10.0,
    ) -> None:
        """
        Wait for a task to complete by monitoring the browser tab.

        Args:
            task: Task being executed
            tab_index: Index of the tab running the task
            start_time: When task execution started
            timeout: Maximum time to wait in seconds
            check_interval: How often to check for completion
        """
        import time

        check_start = time.time()

        while time.time() - check_start < timeout:
            try:
                # Switch to the task's tab
                await self.browser.switch_tab(tab_index)

                # Check for completion indicators
                page_text = await self.browser.get_text("body")

                completion_indicators = [
                    "completed",
                    "finished",
                    "done",
                    "push",
                ]

                page_text_lower = page_text.lower()
                if any(indicator in page_text_lower for indicator in completion_indicators):
                    logger.info(f"Task {task.id} appears to be complete")
                    return

                # Update progress based on elapsed time
                elapsed = (datetime.now() - start_time).total_seconds()
                # Progress from 0.4 to 0.9 based on time elapsed
                progress = min(0.9, 0.4 + (0.5 * (time.time() - check_start) / timeout))
                self.app.update_execution(
                    task=task,
                    progress=progress,
                    elapsed=elapsed,
                    retries=task.retry_count,
                )

                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.debug(f"Error checking task completion: {e}")
                await asyncio.sleep(check_interval)

        logger.warning(f"Task {task.id} completion check timed out after {timeout}s")
        logger.info("Task may still be running - check the browser tab manually")

    def _show_completion(self) -> None:
        """Show completion summary."""
        total_time = (datetime.now() - self.start_time).total_seconds()

        completed = sum(
            1 for t in self.task_list.tasks if t.status == TaskStatus.COMPLETED
        )
        failed = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.FAILED)
        skipped = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.SKIPPED)

        summary = (
            f"Execution Complete!\n\n"
            f"Completed: {completed}\n"
            f"Failed: {failed}\n"
            f"Skipped: {skipped}\n"
            f"Total Time: {int(total_time // 60)}m {int(total_time % 60)}s"
        )

        self.app.notify(summary, title="🎭 Conductor Complete", timeout=0)

    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self.browser:
            await self.browser.close()

        if self.mcp_client and self.mcp_client.is_connected:
            await self.mcp_client.disconnect()

        self.app.notify("Cleanup complete", title="Shutdown")


async def run_with_tui(config: Config, task_list: TaskList) -> None:
    """
    Run orchestrator with TUI.

    Args:
        config: Configuration
        task_list: Tasks to execute
    """
    # STEP 1: Do browser authentication BEFORE creating TUI
    # This prevents the TUI from getting stuck waiting for auth callbacks
    logger.info("Initializing MCP and authenticating BEFORE starting TUI...")

    # Initialize MCP client
    mcp_client = MCPClient(
        server_url=config.mcp.server_url,
        timeout=config.mcp.timeout,
        max_retries=config.mcp.max_retries,
    )

    await mcp_client.connect()
    browser = BrowserController(mcp_client)

    # Run authentication flow
    print("\n🔐 Opening browser for authentication...")
    print("Please log in to Claude Code, then press Enter in this terminal.\n")

    auth_flow = AuthenticationFlow(
        browser=browser,
        timeout=config.auth.timeout,
        check_interval=config.auth.check_interval,
    )

    status = await auth_flow.start(
        headless=config.auth.headless,
        wait_for_user_input=True
    )

    if status != AuthStatus.AUTHENTICATED:
        print(f"\n❌ Authentication failed: {status}")
        await browser.close()
        await mcp_client.disconnect()
        raise RuntimeError(f"Authentication failed: {status}")

    print("✅ Authentication successful!\n")

    # STEP 2: Now that we're authenticated, create and run TUI
    app = ConductorTUI(task_list=task_list)

    # Create orchestrator with pre-authenticated browser
    orchestrator = TUIOrchestrator(config, task_list, app)
    orchestrator.mcp_client = mcp_client
    orchestrator.browser = browser
    orchestrator.auth_flow = auth_flow

    # Run orchestrator in background
    async def run_orchestrator():
        await orchestrator.run()
        # Keep app running after orchestration completes
        await asyncio.sleep(5)
        app.exit()

    # Start orchestrator as background task
    asyncio.create_task(run_orchestrator())

    # Run the TUI app
    await app.run_async()
