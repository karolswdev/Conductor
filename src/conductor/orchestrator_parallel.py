"""
Parallel orchestrator for concurrent task execution.
Implements configurable parallel execution with semaphore-based concurrency control.
"""

import asyncio
import logging
from typing import Optional, List, Dict
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

        # Track running tasks
        self.running_tasks: Dict[str, Task] = {}
        self.completed_tasks: List[Task] = []
        self.failed_tasks: List[Task] = []

        # MCP clients - one per parallel slot
        self.mcp_clients: List[MCPClient] = []
        self.browsers: List[BrowserController] = []

    async def run(self) -> None:
        """Run parallel orchestration."""
        try:
            if self.app:
                self.app.notify(
                    f"Starting Parallel Orchestrator ({self.max_parallel} concurrent tasks)",
                    title="🎭 Conductor",
                )

            logger.info(f"Parallel execution enabled: {self.max_parallel} max concurrent tasks")

            # Step 1: Initialize MCP connections pool
            await self._initialize_mcp_pool()

            # Step 2: Authenticate (using first browser)
            await self._authenticate()

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

    async def _initialize_mcp_pool(self) -> None:
        """Initialize pool of MCP clients and browsers."""
        if self.app:
            self.app.notify(
                f"Initializing {self.max_parallel} browser sessions...", title="MCP"
            )

        for i in range(self.max_parallel):
            try:
                client = MCPClient(
                    server_url=self.config.mcp.server_url,
                    timeout=self.config.mcp.timeout,
                    max_retries=self.config.mcp.max_retries,
                )

                await client.connect()
                browser = BrowserController(client)

                self.mcp_clients.append(client)
                self.browsers.append(browser)

                logger.info(f"Initialized MCP client {i + 1}/{self.max_parallel}")

            except Exception as e:
                logger.error(f"Failed to initialize MCP client {i + 1}: {e}")
                # Continue with available clients

        if not self.mcp_clients:
            raise RuntimeError("Failed to initialize any MCP clients")

        if self.app:
            self.app.notify(
                f"Initialized {len(self.mcp_clients)} browser sessions",
                title="MCP",
                severity="information",
            )

    async def _authenticate(self) -> None:
        """Run authentication flow using first browser."""
        if self.app:
            self.app.notify(
                "Please log in to Claude Code in the browser",
                title="Authentication",
                timeout=10,
            )

        # Use first browser for authentication
        auth_flow = AuthenticationFlow(
            browser=self.browsers[0],
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
            # Get an available browser (round-robin)
            browser_index = len(self.running_tasks) % len(self.browsers)
            browser = self.browsers[browser_index]

            # Track running task
            self.running_tasks[task.id] = task

            # Update TUI
            if self.app:
                self.app.update_task_queue(current_task_id=task.id)

            try:
                await self._execute_task_with_retry(task, browser)
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
        # Simulate task execution with progress updates
        # TODO: Replace with actual Claude Code interaction
        steps = 10
        for step in range(steps + 1):
            progress = step / steps
            elapsed = (datetime.now() - start_time).total_seconds()

            if self.app:
                self.app.update_execution(
                    task=task,
                    progress=progress,
                    elapsed=elapsed,
                    retries=task.retry_count,
                )

            await asyncio.sleep(0.5)

        # Create session
        session_id = f"session_{task.id}_{int(datetime.now().timestamp())}"
        branch_name = f"claude/{task.id.lower()}-{int(datetime.now().timestamp())}"

        self.session_manager.add_session(
            session_id=session_id,
            task_id=task.id,
            branch_name=branch_name,
            url=f"https://claude.ai/code/{session_id}",
        )

        # Update browser preview
        if self.app:
            self.app.update_browser(
                url=f"https://claude.ai/code/{session_id}",
                branch=branch_name,
                preview=f"Task {task.id} completed",
            )

        task.complete(session_id=session_id, branch_name=branch_name)

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
        """Clean up all resources."""
        logger.info("Cleaning up parallel orchestrator resources")

        # Close all browsers
        for browser in self.browsers:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

        # Disconnect all MCP clients
        for client in self.mcp_clients:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting MCP client: {e}")

        if self.app:
            self.app.notify("Cleanup complete", title="Shutdown")


async def run_with_tui_parallel(config: Config, task_list: TaskList) -> None:
    """
    Run parallel orchestrator with TUI.

    Args:
        config: Configuration
        task_list: Tasks to execute
    """
    from conductor.tui.app import ConductorTUI

    app = ConductorTUI(task_list=task_list)

    # Create parallel orchestrator
    orchestrator = ParallelOrchestrator(config, task_list, app)

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
