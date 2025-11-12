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
        Execute a single task.

        This is a simplified version that simulates task execution.
        Future sprints will implement actual Claude Code interaction.

        Args:
            task: Task to execute
        """
        task.start()

        # TODO: Implement actual task execution through Claude Code
        # For now, simulate execution
        await asyncio.sleep(1.0)

        # Simulate session creation
        session_id = f"session_{task.id}"
        branch_name = f"claude/{task.id}"

        self.session_manager.add_session(
            session_id=session_id,
            task_id=task.id,
            branch_name=branch_name,
            url=f"https://claude.ai/code/{session_id}",
        )

        task.complete(session_id=session_id, branch_name=branch_name)

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
