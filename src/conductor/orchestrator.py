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

            # Wait for page to load
            await asyncio.sleep(3.0)

            # Step 4: Select repository if specified
            if hasattr(task, 'repository') and task.repository:
                await self._select_repository(task.repository)

            # Step 5: Fill and submit the prompt
            await self._submit_prompt(task.prompt)

            # Step 6: Wait for session URL to update
            await asyncio.sleep(3.0)
            current_url = await self.browser.get_current_url()
            logger.info(f"Task {task.id} session URL: {current_url}")

            # Extract session ID from URL (format: https://claude.ai/code/session_<id>)
            session_id = self._extract_session_id_from_url(current_url)

            # Step 7: Dismiss notification dialog if present
            await self.browser.dismiss_notification_dialog()

            # Step 8: Monitor for completion (respect task timeout)
            timeout = getattr(task, 'timeout', 600)  # Default 10 minutes
            logger.info(f"Waiting for task {task.id} to complete (timeout: {timeout}s)...")
            await self._wait_for_task_completion(task, tab_index, timeout=timeout)

            # Step 9: Extract branch name from the session
            try:
                page_text = await self.browser.get_text("body")
                branch_name = self.browser.extract_branch_name(page_text)
                if not branch_name:
                    # Fallback to constructed name
                    branch_name = f"claude/{task.id}-{session_id[:8] if session_id else 'unknown'}"
            except Exception as e:
                logger.debug(f"Could not extract branch name: {e}")
                branch_name = f"claude/{task.id}"

            # Step 10: Record the session
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

    async def _select_repository(self, repository: str) -> None:
        """
        Select repository from dropdown.

        Args:
            repository: Repository path (e.g., "owner/repo")
        """
        try:
            logger.info(f"Selecting repository: {repository}")

            # Click repository selector button
            await self.browser.click("Select repository button")
            await asyncio.sleep(2.0)

            # Parse repository path
            parts = repository.split('/')
            if len(parts) >= 2:
                owner = parts[0]
                repo_name = parts[1]
            else:
                # If no slash, assume it's just the repo name
                repo_name = repository
                owner = ""

            # Click the repository option in dropdown
            # Format in dropdown is "reponame owner"
            if owner:
                await self.browser.click(f"{repo_name} {owner} repository option")
            else:
                await self.browser.click(f"{repo_name} repository option")

            await asyncio.sleep(1.0)
            logger.info(f"Repository {repository} selected")

        except Exception as e:
            logger.warning(f"Could not select repository {repository}: {e}")
            # Continue anyway - might already have a repo selected

    async def _submit_prompt(self, prompt: str) -> None:
        """
        Fill and submit the task prompt.

        Args:
            prompt: The task prompt text
        """
        logger.info("Submitting task prompt")
        try:
            # Fill the message input
            await self.browser.fill("Message input textbox", prompt)
            await asyncio.sleep(1.0)

            # Click submit button (will be enabled after text is entered)
            await self.browser.click("Submit button")
            logger.info("Prompt submitted successfully")

        except Exception as e:
            logger.error(f"Could not submit prompt: {e}")
            raise

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

        logger.info(f"Waiting up to {timeout}s for task {task.id} to complete")

        while time.time() - start_time < timeout:
            try:
                # Switch to the task's tab
                await self.browser.switch_tab(tab_index)

                # Get page snapshot/text to check for completion
                page_text = await self.browser.get_text("body")

                # Primary indicator: Check if "Create PR" button is enabled
                if self.browser.is_create_pr_button_enabled(page_text):
                    logger.info(f"Task {task.id} completed - Create PR button enabled")
                    return

                # Secondary indicators: Look for branch name pattern
                if self.browser.extract_branch_name(page_text):
                    # Also check for other completion signs
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

                # Log progress
                elapsed = int(time.time() - start_time)
                if elapsed % 30 == 0:  # Log every 30 seconds
                    logger.debug(f"Task {task.id} still running ({elapsed}s elapsed)")

                # Wait before next check
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.debug(f"Error checking task completion: {e}")
                await asyncio.sleep(check_interval)

        logger.warning(f"Task {task.id} timed out after {timeout}s")
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
