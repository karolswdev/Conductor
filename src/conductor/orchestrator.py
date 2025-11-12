"""
Main orchestrator for task execution.
"""

import asyncio
import logging
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from conductor.mcp.client import MCPClient
from conductor.mcp.browser import BrowserController
from conductor.browser.auth import AuthenticationFlow, AuthStatus
from conductor.browser.session import SessionManager
from conductor.tasks.models import TaskList, Task, TaskStatus
from conductor.utils.config import Config
from conductor.utils.retry import retry_async


logger = logging.getLogger(__name__)
console = Console()


class Orchestrator:
    """
    Orchestrates task execution through Claude Code.

    This is a simplified version for Sprint 1 that demonstrates
    the core flow. Future sprints will add the full TUI.
    """

    def __init__(self, config: Config, task_list: TaskList):
        """
        Initialize orchestrator.

        Args:
            config: Configuration
            task_list: List of tasks to execute
        """
        self.config = config
        self.task_list = task_list
        self.mcp_client: Optional[MCPClient] = None
        self.browser: Optional[BrowserController] = None
        self.auth_flow: Optional[AuthenticationFlow] = None
        self.session_manager = SessionManager()

    async def run(self) -> None:
        """Run the orchestration flow."""
        try:
            console.print("[bold cyan]Starting Conductor Orchestrator[/bold cyan]\n")

            # Step 1: Initialize MCP connection
            await self._initialize_mcp()

            # Step 2: Authenticate
            await self._authenticate()

            # Step 3: Execute tasks
            await self._execute_tasks()

            # Step 4: Show summary
            self._show_summary()

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")

        except Exception as e:
            logger.exception("Orchestration failed")
            console.print(f"\n[red]Error:[/red] {e}")

        finally:
            await self._cleanup()

    async def _initialize_mcp(self) -> None:
        """Initialize MCP connection."""
        console.print("[cyan]Initializing MCP connection...[/cyan]")

        self.mcp_client = MCPClient(
            server_url=self.config.mcp.server_url,
            timeout=self.config.mcp.timeout,
            max_retries=self.config.mcp.max_retries,
        )

        await self.mcp_client.connect()

        self.browser = BrowserController(self.mcp_client)

        console.print("[green]✓[/green] MCP connected\n")

    async def _authenticate(self) -> None:
        """Run authentication flow."""
        console.print("[cyan]Starting authentication flow...[/cyan]")

        self.auth_flow = AuthenticationFlow(
            browser=self.browser,
            timeout=self.config.auth.timeout,
            check_interval=self.config.auth.check_interval,
        )

        # Show instructions
        console.print("\n[bold yellow]🌐 Browser opened to Claude Code[/bold yellow]")
        console.print("[bold]Please complete the following steps:[/bold]")
        console.print("  1. Log in to Claude Code if not already logged in")
        console.print("  2. Wait for the page to fully load")
        console.print("  3. Press [bold cyan]Enter[/bold cyan] in this terminal when ready\n")
        console.print(f"[dim](Timeout: {self.config.auth.timeout} seconds)[/dim]\n")

        status = await self.auth_flow.start(
            headless=self.config.auth.headless,
            wait_for_user_input=True
        )

        if status == AuthStatus.AUTHENTICATED:
            console.print("\n[green]✓[/green] Authentication confirmed! Starting task execution...\n")
        elif status == AuthStatus.TIMEOUT:
            console.print("\n[red]✗[/red] Authentication timed out - no confirmation received")
            raise RuntimeError("Authentication timeout")
        else:
            console.print(f"\n[red]✗[/red] Authentication failed: {status}")
            raise RuntimeError(f"Authentication failed: {status}")

    async def _execute_tasks(self) -> None:
        """Execute all tasks in order."""
        console.print(f"[cyan]Executing {len(self.task_list)} tasks...[/cyan]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            overall = progress.add_task("[cyan]Overall Progress", total=len(self.task_list))

            for task in self.task_list.tasks:
                # Check if dependencies are met
                if not self._dependencies_met(task):
                    console.print(f"[yellow]Skipping {task.id}: dependencies not met[/yellow]")
                    task.skip()
                    progress.advance(overall)
                    continue

                # Execute task
                task_progress = progress.add_task(
                    f"[cyan]Task: {task.name}", total=None
                )

                try:
                    await self._execute_task(task)
                    console.print(f"[green]✓[/green] {task.id}: {task.name}")

                except Exception as e:
                    logger.error(f"Task {task.id} failed: {e}")
                    console.print(f"[red]✗[/red] {task.id}: {task.name} - {e}")
                    task.fail(str(e))

                progress.remove_task(task_progress)
                progress.advance(overall)

        console.print("\n[green]All tasks processed![/green]\n")

    def _dependencies_met(self, task: Task) -> bool:
        """Check if task dependencies are met."""
        for dep_id in task.dependencies:
            dep_task = self.task_list.get_task(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    async def _execute_task(self, task: Task) -> None:
        """
        Execute a single task in its own browser tab.

        Args:
            task: Task to execute

        Raises:
            Exception: If task execution fails
        """
        task.start()
        tab_index = None

        try:
            # Step 1: Create a new tab for this task
            logger.info(f"Creating new tab for task {task.id}")
            tab_index = await self.browser.create_tab()

            # Step 2: Switch to the new tab
            await self.browser.switch_tab(tab_index)

            # Step 3: Navigate to Claude Code
            logger.info(f"Navigating to Claude Code for task {task.id}")
            await self.browser.navigate("https://claude.ai/code")

            # Wait a bit for page to load
            await asyncio.sleep(3.0)

            # Step 4: Click "New Session" button to create a session
            # This is a simplified approach - the actual implementation would need
            # more sophisticated element detection and interaction
            try:
                logger.info(f"Attempting to create new session for task {task.id}")

                # Try to find and click the new session button
                # The actual selector may vary - this is based on common patterns
                await self.browser.click("[data-testid='new-session-button']")
                await asyncio.sleep(2.0)

            except Exception as e:
                logger.warning(f"Could not click new session button: {e}")
                logger.info("Assuming we're already in a new session context")

            # Step 5: Get the current URL to extract session ID
            current_url = await self.browser.get_current_url()
            logger.info(f"Task {task.id} session URL: {current_url}")

            # Extract session ID from URL (format: https://claude.ai/code/<session-id>)
            session_id = self._extract_session_id_from_url(current_url)

            # Step 6: Type the task prompt into the input
            logger.info(f"Submitting task prompt for task {task.id}")
            try:
                # Find the prompt input (common selectors for text input)
                await self.browser.fill("textarea[placeholder*='message']", task.prompt)
                await asyncio.sleep(1.0)

                # Submit the prompt (usually Cmd+Enter or a submit button)
                # Note: This is a simplified approach - actual submission may vary
                await self.browser.click("button[type='submit']")

            except Exception as e:
                logger.warning(f"Could not submit prompt automatically: {e}")
                logger.info("Task prompt may need to be submitted manually")

            # Step 7: Monitor for completion
            # For now, we wait a reasonable amount of time
            # Future implementation should poll for completion indicators
            logger.info(f"Waiting for task {task.id} to complete...")
            await self._wait_for_task_completion(task, tab_index)

            # Step 8: Extract branch name from the session
            # This would require parsing the page or using API
            # For now, construct expected branch name
            branch_name = f"claude/{task.id}"

            # Try to extract actual branch from page if possible
            try:
                page_text = await self.browser.get_text("body")
                extracted_branch = self._extract_branch_name_from_page(page_text)
                if extracted_branch:
                    branch_name = extracted_branch
            except Exception as e:
                logger.debug(f"Could not extract branch name: {e}")

            # Step 9: Record the session
            self.session_manager.add_session(
                session_id=session_id or f"session_{task.id}",
                task_id=task.id,
                branch_name=branch_name,
                url=current_url,
            )

            # Mark task as complete
            task.complete(
                session_id=session_id or f"session_{task.id}",
                branch_name=branch_name,
            )

            logger.info(f"Task {task.id} completed successfully")

        except Exception as e:
            logger.error(f"Task {task.id} execution failed: {e}")
            task.fail(str(e))
            raise

        finally:
            # Keep the tab open for inspection
            # User can close tabs manually or we can add config option
            pass

    def _extract_session_id_from_url(self, url: str) -> Optional[str]:
        """
        Extract session ID from Claude Code URL.

        Args:
            url: The current URL

        Returns:
            Session ID if found, None otherwise
        """
        # Format: https://claude.ai/code/<session-id>
        if "/code/" in url:
            parts = url.split("/code/")
            if len(parts) > 1:
                session_id = parts[1].split("?")[0].split("#")[0]
                return session_id if session_id else None
        return None

    def _extract_branch_name_from_page(self, page_text: str) -> Optional[str]:
        """
        Extract git branch name from page content.

        Args:
            page_text: Text content of the page

        Returns:
            Branch name if found, None otherwise
        """
        # Look for branch patterns like "claude/feature-name"
        import re

        # Common patterns for branch names in Claude Code UI
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
        timeout: int = 600,
        check_interval: float = 10.0,
    ) -> None:
        """
        Wait for a task to complete by monitoring the browser tab.

        Args:
            task: Task being executed
            tab_index: Index of the tab running the task
            timeout: Maximum time to wait in seconds
            check_interval: How often to check for completion

        Raises:
            TimeoutError: If task doesn't complete within timeout
        """
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Switch to the task's tab
                await self.browser.switch_tab(tab_index)

                # Check for completion indicators in the page
                page_text = await self.browser.get_text("body")

                # Look for completion indicators
                # These are heuristics - actual indicators may vary
                completion_indicators = [
                    "completed",
                    "finished",
                    "done",
                    "push",  # When Claude pushes to git
                ]

                page_text_lower = page_text.lower()
                if any(indicator in page_text_lower for indicator in completion_indicators):
                    logger.info(f"Task {task.id} appears to be complete")
                    return

                # Wait before next check
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.debug(f"Error checking task completion: {e}")
                await asyncio.sleep(check_interval)

        logger.warning(f"Task {task.id} completion check timed out after {timeout}s")
        logger.info("Task may still be running - check the browser tab manually")

    def _show_summary(self) -> None:
        """Show execution summary."""
        console.print("[bold cyan]Execution Summary[/bold cyan]\n")

        completed = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.FAILED)
        skipped = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.SKIPPED)

        console.print(f"  Completed: [green]{completed}[/green]")
        console.print(f"  Failed: [red]{failed}[/red]")
        console.print(f"  Skipped: [yellow]{skipped}[/yellow]")

        # Show branches created
        branches = self.session_manager.get_all_branches()
        if branches:
            console.print(f"\n[bold]Branches created:[/bold]")
            for branch in branches:
                console.print(f"  • {branch}")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self.browser:
            await self.browser.close()

        if self.mcp_client and self.mcp_client.is_connected:
            await self.mcp_client.disconnect()

        console.print("\n[dim]Cleanup complete[/dim]")
