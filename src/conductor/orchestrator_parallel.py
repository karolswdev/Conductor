"""
Parallel orchestrator for concurrent task execution.
Implements configurable parallel execution with semaphore-based concurrency control.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Callable, Awaitable, Any
from datetime import datetime

from conductor.mcp.client import MCPClient
from conductor.mcp.browser import BrowserController
from conductor.browser.auth import AuthenticationFlow, AuthStatus
from conductor.browser.session import SessionManager
from conductor.tasks.models import TaskList, Task, TaskStatus
from conductor.utils.config import Config
from conductor.utils.retry import exponential_backoff
from conductor.tui.app import ConductorTUI


logger = logging.getLogger(__name__)


class ParallelOrchestrator:
    """
    Orchestrates parallel task execution with configurable concurrency.

    Features:
    - Semaphore-based concurrency control
    - Configurable max parallel tasks (1-10)
    - Independent browser sessions per task
    - Real-time TUI updates for all running tasks
    - Proper resource cleanup
    """

    def __init__(self, config: Config, task_list: TaskList, app: Optional[ConductorTUI] = None):
        """
        Initialize parallel orchestrator.

        Args:
            config: Configuration with execution.max_parallel_tasks
            task_list: List of tasks to execute
            app: Optional TUI application instance
        """
        self.config = config
        self.task_list = task_list
        self.app = app
        self.session_manager = SessionManager()
        self.start_time = datetime.now()

        # Concurrency control
        self.max_parallel = config.execution.max_parallel_tasks
        self.semaphore = asyncio.Semaphore(self.max_parallel)

        # Lock browser interactions to prevent tasks from stomping on each other
        self.browser_lock = asyncio.Lock()

        # Track running tasks
        self.running_tasks: Dict[str, Task] = {}
        self.completed_tasks: List[Task] = []
        self.failed_tasks: List[Task] = []

        # Single MCP client and browser (shared with all tasks)
        self.mcp_client: Optional[MCPClient] = None
        self.browser: Optional[BrowserController] = None

    async def _run_in_tab(
        self,
        browser: BrowserController,
        tab_index: int,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs,
    ) -> Any:
        """
        Safely run a browser action scoped to a specific tab.

        Ensures the tab is selected and no other task interferes mid-action.
        """
        async with self.browser_lock:
            await browser.switch_tab(tab_index)
            return await func(*args, **kwargs)

    async def run(self) -> None:
        """Run parallel orchestration."""
        try:
            if self.app:
                self.app.notify(
                    f"Starting Parallel Orchestrator ({self.max_parallel} concurrent tasks)",
                    title="🎭 Conductor",
                )

            logger.info(f"Parallel execution enabled: {self.max_parallel} max concurrent tasks")

            # Step 1: Initialize MCP connection (skip if already initialized)
            if not self.mcp_client:
                await self._initialize_mcp()

            # Step 2: Authenticate (skip if already authenticated by pre-init)
            if not self.browser:
                await self._authenticate()
            else:
                if self.app:
                    self.app.notify(
                        "Already authenticated!", title="Auth", severity="information"
                    )

            # Step 3: Execute tasks in parallel
            await self._execute_tasks_parallel()

            # Step 4: Show completion
            self._show_completion()

        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            if self.app:
                self.app.notify("Interrupted by user", title="Warning", severity="warning")

        except Exception as e:
            logger.exception("Parallel orchestration failed")
            if self.app:
                self.app.notify(f"Error: {str(e)}", title="Orchestration Failed", severity="error")

        finally:
            await self._cleanup()

    async def _initialize_mcp(self) -> None:
        """Initialize single MCP connection and browser."""
        if self.app:
            self.app.notify("Initializing MCP connection...", title="MCP")

        self.mcp_client = MCPClient(
            server_url=self.config.mcp.server_url,
            timeout=self.config.mcp.timeout,
            max_retries=self.config.mcp.max_retries,
        )

        await self.mcp_client.connect()
        self.browser = BrowserController(self.mcp_client)

        if self.app:
            self.app.notify("MCP connected successfully", title="MCP", severity="information")

    async def _authenticate(self) -> None:
        """Run authentication flow."""
        if self.app:
            self.app.notify(
                "Browser opening - log in to Claude Code, then press Enter in terminal",
                title="Authentication",
                timeout=10,
            )

        auth_flow = AuthenticationFlow(
            browser=self.browser,
            timeout=self.config.auth.timeout,
            check_interval=self.config.auth.check_interval,
        )

        status = await auth_flow.start(
            headless=self.config.auth.headless,
            wait_for_user_input=True
        )

        if status == AuthStatus.AUTHENTICATED:
            if self.app:
                self.app.notify(
                    "Authentication successful!", title="Auth", severity="information"
                )
        else:
            error_msg = f"Authentication failed: {status}"
            if self.app:
                self.app.notify(error_msg, title="Auth", severity="error")
            raise RuntimeError(error_msg)

    async def _execute_tasks_parallel(self) -> None:
        """Execute tasks in parallel with concurrency control."""
        if self.app:
            self.app.notify(
                f"Executing {len(self.task_list)} tasks (max {self.max_parallel} parallel)",
                title="Execution",
            )

        # Create tasks for all runnable tasks
        task_coroutines = []

        for task in self.task_list.tasks:
            # Only start tasks that have no dependencies or whose dependencies are met
            if not task.dependencies:
                task_coroutines.append(self._execute_task_with_semaphore(task))

        # Wait for all initial tasks to complete
        if task_coroutines:
            await asyncio.gather(*task_coroutines, return_exceptions=True)

        # Process dependent tasks as their dependencies complete
        await self._process_dependent_tasks()

        if self.app:
            self.app.notify("All tasks processed!", title="Complete", severity="information")

    async def _process_dependent_tasks(self) -> None:
        """Process tasks that have dependencies."""
        max_iterations = len(self.task_list) * 2  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Find tasks that are now runnable
            runnable = []
            for task in self.task_list.tasks:
                if task.status != TaskStatus.PENDING:
                    continue

                # Check if all dependencies are completed
                deps_met = all(
                    self.task_list.get_task(dep_id).status == TaskStatus.COMPLETED
                    for dep_id in task.dependencies
                )

                if deps_met:
                    runnable.append(task)

            if not runnable:
                break  # No more runnable tasks

            # Execute runnable tasks
            coroutines = [
                self._execute_task_with_semaphore(task) for task in runnable
            ]
            await asyncio.gather(*coroutines, return_exceptions=True)

    async def _execute_task_with_semaphore(self, task: Task) -> None:
        """
        Execute a single task with semaphore control.

        Args:
            task: Task to execute
        """
        async with self.semaphore:
            # Track running task
            self.running_tasks[task.id] = task

            # Update TUI
            if self.app:
                self.app.update_task_queue(current_task_id=task.id)

            try:
                # Use the shared browser - tasks will time-slice via the browser lock
                await self._execute_task_with_retry(task, self.browser)
                self.completed_tasks.append(task)

                if self.app:
                    self.app.notify(
                        f"Task {task.id} completed",
                        title="Success",
                        severity="information",
                    )

            except Exception as e:
                logger.error(f"Task {task.id} failed: {e}")
                task.fail(str(e))
                self.failed_tasks.append(task)

                if self.app:
                    self.app.notify(
                        f"Task {task.id} failed: {str(e)}",
                        title="Task Failed",
                        severity="error",
                    )

            finally:
                # Remove from running tasks
                self.running_tasks.pop(task.id, None)

                # Update TUI
                if self.app:
                    self.app.update_task_queue()
                    self.app.update_metrics()

    async def _execute_task_with_retry(self, task: Task, browser: BrowserController) -> None:
        """
        Execute a task with retry logic.

        Args:
            task: Task to execute
            browser: Browser to use
        """
        task.start()
        start_time = datetime.now()

        for attempt in range(task.retry_policy.max_attempts):
            try:
                # Update execution panel
                if self.app:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    self.app.update_execution(
                        task=task,
                        progress=0.0,
                        elapsed=elapsed,
                        retries=attempt,
                    )

                # Execute the task
                await self._execute_single_task(task, browser, start_time)

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

                    if self.app:
                        self.app.notify(
                            f"Retrying {task.id} in {delay:.1f}s (attempt {attempt + 2})",
                            title="Retry",
                            timeout=5,
                        )

                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    raise

    async def _execute_single_task(
        self, task: Task, browser: BrowserController, start_time: datetime
    ) -> None:
        """
        Execute a single task attempt.

        Args:
            task: Task to execute
            browser: Browser to use
            start_time: When execution started
        """
        session_id: Optional[str] = None
        tab_index: Optional[int] = None

        try:
            # Step 1: Create tab (serialize creation to avoid race condition)
            async with self.browser_lock:
                logger.info(f"Creating new tab for task {task.id}")
                tab_index = await browser.create_tab()

            # Give Playwright a moment to register the tab
            await asyncio.sleep(0.5)

            logger.info(f"Switching to tab {tab_index} for task {task.id}")
            await self._run_in_tab(browser, tab_index, browser.navigate, "https://claude.ai/code/new")

            # Wait for page to load fully before interacting
            await asyncio.sleep(3.0)

            # Update progress
            if self.app:
                self.app.update_execution(
                    task=task,
                    progress=0.2,
                    elapsed=(datetime.now() - start_time).total_seconds(),
                    retries=task.retry_count,
                )

            # Step 2: Repository selection (per tab)
            repository = getattr(task, "repository", None) or self.config.default_repository
            if repository:
                try:
                    logger.info(f"Selecting repository: {repository}")
                    try:
                        await self._run_in_tab(browser, tab_index, browser.click, "repository selector button")
                    except Exception:
                        await self._run_in_tab(browser, tab_index, browser.click, "Select repository button")
                    await asyncio.sleep(2.0)

                    parts = repository.split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        repo_name = parts[1]
                        await self._run_in_tab(
                            browser,
                            tab_index,
                            browser.click,
                            f"{repo_name} {owner} repository option",
                        )
                    else:
                        await self._run_in_tab(
                            browser,
                            tab_index,
                            browser.click,
                            f"{repository} repository option",
                        )

                    await asyncio.sleep(1.0)
                except Exception as e:
                    logger.warning(f"Could not select repository: {e}")

            # Update progress
            if self.app:
                self.app.update_execution(
                    task=task,
                    progress=0.3,
                    elapsed=(datetime.now() - start_time).total_seconds(),
                    retries=task.retry_count,
                )

            # Step 3: Submit task prompt
            logger.info(f"Submitting task prompt for task {task.id}")
            try:
                await self._run_in_tab(
                    browser,
                    tab_index,
                    browser.fill,
                    "Message input textbox",
                    task.prompt,
                )
                await asyncio.sleep(1.0)
                await self._run_in_tab(browser, tab_index, browser.click, "Submit button")
                await asyncio.sleep(3.0)
                current_url = await self._run_in_tab(browser, tab_index, browser.get_current_url)
                session_source = self._normalize_session_url(current_url) or current_url or ""
                session_id = self._extract_session_id_from_url(session_source)
                await self._run_in_tab(browser, tab_index, browser.dismiss_notification_dialog)
            except Exception as e:
                logger.warning(f"Could not submit prompt automatically: {e}")
                raise

            # Update progress
            if self.app:
                self.app.update_execution(
                    task=task,
                    progress=0.4,
                    elapsed=(datetime.now() - start_time).total_seconds(),
                    retries=task.retry_count,
                )

            # Step 5: Monitor for completion
            logger.info(f"Waiting for task {task.id} to complete...")
            await self._wait_for_task_completion(task, browser, tab_index, start_time)

            # Update progress
            if self.app:
                self.app.update_execution(
                    task=task,
                    progress=0.9,
                    elapsed=(datetime.now() - start_time).total_seconds(),
                    retries=task.retry_count,
                )

            # Step 6: Extract branch name
            branch_name = f"claude/{task.id.lower()}"
            try:
                page_text = await self._run_in_tab(browser, tab_index, browser.get_text, "body")
                # Use browser's extract_branch_name method which looks for the correct pattern
                extracted_branch = browser.extract_branch_name(page_text)
                if extracted_branch:
                    branch_name = extracted_branch
                else:
                    # Fallback: try the old extraction method
                    extracted_branch = self._extract_branch_name_from_page(page_text)
                    if extracted_branch:
                        branch_name = extracted_branch
            except Exception as e:
                logger.debug(f"Could not extract branch name: {e}")

            # Step 7: Record session
            final_url = await self._run_in_tab(browser, tab_index, browser.get_current_url)
            self.session_manager.add_session(
                session_id=session_id or f"session_{task.id}_{int(datetime.now().timestamp())}",
                task_id=task.id,
                branch_name=branch_name,
                url=final_url,
            )

            # Update browser preview
            if self.app:
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

    def _normalize_session_url(self, url: Optional[str]) -> Optional[str]:
        """Clean up the browser-reported URL."""
        if not url:
            return None

        cleaned = url.strip().strip('"')
        return cleaned or None

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
        browser: BrowserController,
        tab_index: int,
        start_time: datetime,
        timeout: int = 600,
        check_interval: float = 10.0,
    ) -> None:
        """
        Wait for a task to complete by periodically loading its session.

        Args:
            task: Task being executed
            browser: Browser controller
            session_url: URL of the Claude session for this task
            start_time: When task execution started
            timeout: Maximum time to wait in seconds
            check_interval: How often to check for completion
        """
        import time

        # Use task-specific timeout if available
        if hasattr(task, 'timeout'):
            timeout = task.timeout

        check_start = time.time()
        logger.info(f"Waiting up to {timeout}s for task {task.id} to complete")

        while time.time() - check_start < timeout:
            try:
                page_text = await self._run_in_tab(browser, tab_index, browser.get_text, "body")

                # Primary indicator: Check if "Create PR" button is enabled
                if browser.is_create_pr_button_enabled(page_text):
                    logger.info(f"Task {task.id} completed - Create PR button enabled")
                    return

                # Secondary indicators: Look for branch name and completion keywords
                if browser.extract_branch_name(page_text):
                    completion_keywords = [
                        "pushed to branch",
                        "create pr",
                        "pull request",
                        "committed",
                        "merged"
                    ]
                    page_text_lower = page_text.lower()
                    if any(keyword in page_text_lower for keyword in completion_keywords):
                        logger.info(f"Task {task.id} appears to be complete (branch created)")
                        return

                # Update progress based on elapsed time
                if self.app:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    # Progress from 0.4 to 0.9 based on time elapsed
                    progress = min(0.9, 0.4 + (0.5 * (time.time() - check_start) / timeout))
                    self.app.update_execution(
                        task=task,
                        progress=progress,
                        elapsed=elapsed,
                        retries=task.retry_count,
                    )

                # Log progress periodically
                elapsed_total = int(time.time() - check_start)
                if elapsed_total % 30 == 0:  # Log every 30 seconds
                    logger.debug(f"Task {task.id} still running ({elapsed_total}s elapsed)")

                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.debug(f"Error checking task completion: {e}")
                await asyncio.sleep(check_interval)

        logger.warning(f"Task {task.id} timed out after {timeout}s")
        logger.info("Task may still be running - check the Claude session manually")

    def _show_completion(self) -> None:
        """Show completion summary."""
        total_time = (datetime.now() - self.start_time).total_seconds()

        completed = len(self.completed_tasks)
        failed = len(self.failed_tasks)
        skipped = sum(
            1 for t in self.task_list.tasks if t.status == TaskStatus.SKIPPED
        )

        summary = (
            f"Parallel Execution Complete!\n\n"
            f"Completed: {completed}\n"
            f"Failed: {failed}\n"
            f"Skipped: {skipped}\n"
            f"Total Time: {int(total_time // 60)}m {int(total_time % 60)}s\n"
            f"Max Parallel: {self.max_parallel}"
        )

        logger.info(summary)

        if self.app:
            self.app.notify(summary, title="🎭 Conductor Complete", timeout=0)

    async def _cleanup(self) -> None:
        """Clean up resources.

        Note: If browser/mcp_client were passed in from outside (e.g., pre-authenticated),
        we should NOT close them as they're managed externally.
        """
        logger.info("Cleaning up parallel orchestrator resources")

        # Don't close browser/MCP if they were passed in from outside
        # Check if we initialized them ourselves by seeing if they were None at start
        # For now, just log but don't close - the caller will handle cleanup
        logger.info("Skipping browser/MCP cleanup (managed externally)")

        if self.app:
            self.app.notify("Cleanup complete", title="Shutdown")


async def run_with_tui_parallel(config: Config, task_list: TaskList) -> None:
    """
    Run parallel orchestrator with TUI.
    Uses ONE browser session while juggling multiple Claude session URLs.

    Args:
        config: Configuration
        task_list: Tasks to execute
    """
    from conductor.tui.app import ConductorTUI

    # STEP 1: Do browser authentication BEFORE creating TUI
    # This prevents the TUI from getting stuck waiting for auth callbacks
    logger.info("Initializing MCP and authenticating BEFORE starting TUI...")

    # Initialize single MCP client for all parallel tasks
    print(f"\n🔧 Initializing browser (will juggle {config.execution.max_parallel_tasks} tasks by hopping between sessions)...")

    mcp_client = MCPClient(
        server_url=config.mcp.server_url,
        timeout=config.mcp.timeout,
        max_retries=config.mcp.max_retries,
    )

    await mcp_client.connect()
    browser = BrowserController(mcp_client)

    print("✅ Browser initialized\n")

    # Run authentication flow
    print("🔐 Opening browser for authentication...")
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

    # STEP 2: Now that we're authenticated, create orchestrator and TUI
    logger.info("Creating ParallelOrchestrator...")
    try:
        # Create orchestrator without the app first
        orchestrator = ParallelOrchestrator(config, task_list, app=None)
        orchestrator.mcp_client = mcp_client
        orchestrator.browser = browser
        logger.info(f"ParallelOrchestrator created successfully")
        logger.info(f"  - mcp_client: {orchestrator.mcp_client}")
        logger.info(f"  - browser: {orchestrator.browser}")
    except Exception as e:
        logger.exception("Failed to create ParallelOrchestrator")
        raise

    # Create TUI with orchestrator - TUI will start orchestrator as worker in on_mount()
    logger.info("Creating ConductorTUI with orchestrator...")
    try:
        app = ConductorTUI(task_list=task_list, orchestrator=orchestrator)
        # Set the app reference in orchestrator
        orchestrator.app = app
        logger.info(f"ConductorTUI created successfully: {app}")
    except Exception as e:
        logger.exception("Failed to create ConductorTUI")
        raise

    logger.info("About to start TUI (orchestrator will start as worker in on_mount)...")

    try:
        # Run the TUI app
        # The orchestrator will be started automatically by TUI's on_mount() method
        logger.info("=== STARTING TUI APP ===")
        logger.info("Calling app.run_async()...")
        await app.run_async()
        logger.info("=== TUI APP EXITED ===")

    except Exception as e:
        logger.exception("=== ERROR IN TUI SETUP ===")
        print(f"\n❌ TUI setup failed: {e}\n")
        import traceback
        traceback.print_exc()

    finally:
        # Clean up browser and MCP connection we created
        logger.info("=== CLEANUP STARTED ===")
        if browser:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

        if mcp_client and mcp_client.is_connected:
            try:
                await mcp_client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting MCP client: {e}")
