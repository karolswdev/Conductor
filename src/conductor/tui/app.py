"""
Main Textual TUI application for Conductor.
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Label
from textual.reactive import reactive
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
from typing import Optional, List
from datetime import datetime

from conductor.tasks.models import Task, TaskStatus, TaskList


class TaskQueuePanel(Static):
    """Panel showing the task queue."""

    tasks = reactive(None)
    current_task_id = reactive(None)

    def __init__(self, task_list: Optional[TaskList] = None, **kwargs):
        super().__init__(**kwargs)
        self.task_list = task_list or TaskList()

    def render(self) -> Panel:
        """Render the task queue."""
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("", width=2)
        table.add_column("ID", width=12)
        table.add_column("Name", width=25)
        table.add_column("Status", width=12)

        for task in self.task_list.tasks:
            # Icon based on status
            if task.status == TaskStatus.RUNNING:
                icon = "[yellow]▶[/yellow]"
            elif task.status == TaskStatus.COMPLETED:
                icon = "[green]✓[/green]"
            elif task.status == TaskStatus.FAILED:
                icon = "[red]✗[/red]"
            elif task.status == TaskStatus.SKIPPED:
                icon = "[dim]○[/dim]"
            else:
                icon = "[dim]▷[/dim]"

            # Status color
            status_colors = {
                TaskStatus.RUNNING: "yellow",
                TaskStatus.COMPLETED: "green",
                TaskStatus.FAILED: "red",
                TaskStatus.SKIPPED: "dim",
                TaskStatus.PENDING: "white",
            }
            status_color = status_colors.get(task.status, "white")
            status_text = f"[{status_color}]{task.status.value}[/{status_color}]"

            # Highlight current task
            if task.id == self.current_task_id:
                table.add_row(
                    icon,
                    f"[bold]{task.id}[/bold]",
                    f"[bold]{task.display_name}[/bold]",
                    status_text,
                    style="on blue",
                )
            else:
                table.add_row(icon, task.id, task.display_name, status_text)

        return Panel(
            table,
            title="[bold cyan]Task Queue[/bold cyan]",
            border_style="cyan",
            box=box.DOUBLE,
        )

    def update_tasks(self, task_list: TaskList, current_id: Optional[str] = None):
        """Update the task list."""
        self.task_list = task_list
        self.current_task_id = current_id
        self.refresh()


class ExecutionPanel(Static):
    """Panel showing current execution status."""

    current_task = reactive(None)
    progress = reactive(0.0)
    elapsed_time = reactive(0.0)
    retry_count = reactive(0)

    def render(self) -> Panel:
        """Render the execution panel."""
        if not self.current_task:
            content = Text("No task currently executing", style="dim italic")
        else:
            task = self.current_task
            content = Table(box=None, show_header=False, pad_edge=False)
            content.add_column("Key", style="cyan", width=12)
            content.add_column("Value", width=40)

            content.add_row("Task ID:", task.id)
            content.add_row("Name:", task.name)
            content.add_row("Status:", self._get_status_text(task.status))

            # Progress bar
            progress_text = self._create_progress_bar(self.progress)
            content.add_row("Progress:", progress_text)

            # Time
            elapsed = f"{int(self.elapsed_time // 60)}:{int(self.elapsed_time % 60):02d}"
            content.add_row("Elapsed:", elapsed)

            # Retries
            max_retries = task.retry_policy.max_attempts
            retry_text = f"{self.retry_count}/{max_retries}"
            if self.retry_count > 0:
                retry_text = f"[yellow]{retry_text}[/yellow]"
            content.add_row("Retries:", retry_text)

            # Branch
            if task.branch_name:
                content.add_row("Branch:", task.branch_name)

        return Panel(
            content,
            title="[bold yellow]Current Execution[/bold yellow]",
            border_style="yellow",
            box=box.DOUBLE,
        )

    def _get_status_text(self, status: TaskStatus) -> str:
        """Get colored status text."""
        colors = {
            TaskStatus.RUNNING: "yellow",
            TaskStatus.COMPLETED: "green",
            TaskStatus.FAILED: "red",
            TaskStatus.PENDING: "white",
            TaskStatus.SKIPPED: "dim",
        }
        color = colors.get(status, "white")
        return f"[{color}]{status.value}[/{color}]"

    def _create_progress_bar(self, progress: float) -> str:
        """Create a text progress bar."""
        width = 30
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
        percent = int(progress * 100)
        return f"{bar} {percent}%"

    def update_execution(
        self,
        task: Optional[Task] = None,
        progress: float = 0.0,
        elapsed: float = 0.0,
        retries: int = 0,
    ):
        """Update execution information."""
        self.current_task = task
        self.progress = progress
        self.elapsed_time = elapsed
        self.retry_count = retries
        self.refresh()


class MetricsPanel(Static):
    """Panel showing execution metrics."""

    total_tasks = reactive(0)
    completed = reactive(0)
    failed = reactive(0)
    skipped = reactive(0)
    avg_time = reactive(0.0)
    total_time = reactive(0.0)

    def render(self) -> Panel:
        """Render metrics panel."""
        table = Table(box=None, show_header=False, pad_edge=False)
        table.add_column("Metric", style="cyan", width=15)
        table.add_column("Value", width=20)

        table.add_row("Total Tasks:", str(self.total_tasks))
        table.add_row(
            "Completed:",
            f"[green]{self.completed}[/green]" if self.completed > 0 else "0",
        )
        table.add_row(
            "Failed:", f"[red]{self.failed}[/red]" if self.failed > 0 else "0"
        )
        table.add_row(
            "Skipped:",
            f"[yellow]{self.skipped}[/yellow]" if self.skipped > 0 else "0",
        )

        # Success rate
        if self.total_tasks > 0:
            success_rate = (self.completed / self.total_tasks) * 100
            color = "green" if success_rate >= 90 else "yellow" if success_rate >= 70 else "red"
            table.add_row("Success Rate:", f"[{color}]{success_rate:.1f}%[/{color}]")

        # Times
        avg_mins = int(self.avg_time // 60)
        avg_secs = int(self.avg_time % 60)
        table.add_row("Avg Time:", f"{avg_mins}m {avg_secs}s")

        total_mins = int(self.total_time // 60)
        total_secs = int(self.total_time % 60)
        table.add_row("Total Time:", f"{total_mins}m {total_secs}s")

        return Panel(
            table,
            title="[bold green]Metrics[/bold green]",
            border_style="green",
            box=box.DOUBLE,
        )

    def update_metrics(
        self,
        total: int = 0,
        completed: int = 0,
        failed: int = 0,
        skipped: int = 0,
        avg_time: float = 0.0,
        total_time: float = 0.0,
    ):
        """Update metrics."""
        self.total_tasks = total
        self.completed = completed
        self.failed = failed
        self.skipped = skipped
        self.avg_time = avg_time
        self.total_time = total_time
        self.refresh()


class BrowserPreviewPanel(Static):
    """Panel showing browser preview."""

    url = reactive("")
    branch = reactive("")
    preview_text = reactive("")

    def render(self) -> Panel:
        """Render browser preview."""
        content = Table(box=None, show_header=False, pad_edge=False)
        content.add_column("Info", width=60)

        if self.url:
            content.add_row(f"[dim]🌐[/dim] {self.url}")

        if self.branch:
            content.add_row(f"[dim]Branch:[/dim] [cyan]{self.branch}[/cyan]")

        if self.preview_text:
            content.add_row("")
            content.add_row(self.preview_text)
        else:
            content.add_row("")
            content.add_row("[dim italic]No preview available[/dim italic]")

        content.add_row("")
        content.add_row(
            "[cyan]Actions:[/cyan] [P]eek  [C]reate PR  [S]kip  [R]etry  [A]bort"
        )

        return Panel(
            content,
            title="[bold magenta]Browser Preview[/bold magenta]",
            border_style="magenta",
            box=box.DOUBLE,
        )

    def update_preview(
        self, url: str = "", branch: str = "", preview: str = ""
    ):
        """Update browser preview."""
        self.url = url
        self.branch = branch
        self.preview_text = preview
        self.refresh()


class ConductorTUI(App):
    """Main Conductor TUI application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #top-container {
        height: 60%;
        dock: top;
    }

    #bottom-container {
        height: 40%;
        dock: bottom;
    }

    .panel-container {
        height: 100%;
    }

    TaskQueuePanel {
        width: 35%;
    }

    ExecutionPanel {
        width: 35%;
    }

    MetricsPanel {
        width: 30%;
    }

    BrowserPreviewPanel {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "peek", "Peek Browser"),
        Binding("c", "create_pr", "Create PR"),
        Binding("s", "skip", "Skip Task"),
        Binding("r", "retry", "Retry"),
        Binding("a", "abort", "Abort"),
        Binding("?", "help", "Help"),
        Binding("up,k", "scroll_up", "Scroll Up", show=False),
        Binding("down,j", "scroll_down", "Scroll Down", show=False),
    ]

    TITLE = "🎭 Conductor - Claude Code Orchestration"

    def __init__(self, task_list: Optional[TaskList] = None, orchestrator=None, **kwargs):
        super().__init__(**kwargs)
        self.task_list = task_list or TaskList()
        self.orchestrator = orchestrator  # Optional orchestrator to run in background
        self.task_queue_panel = None
        self.execution_panel = None
        self.metrics_panel = None
        self.browser_panel = None

    def compose(self) -> ComposeResult:
        """Create the TUI layout."""
        yield Header(show_clock=True)

        # Top container: Task Queue, Execution, Metrics
        with Horizontal(id="top-container"):
            self.task_queue_panel = TaskQueuePanel(self.task_list, classes="panel-container")
            yield self.task_queue_panel

            self.execution_panel = ExecutionPanel(classes="panel-container")
            yield self.execution_panel

            self.metrics_panel = MetricsPanel(classes="panel-container")
            yield self.metrics_panel

        # Bottom container: Browser Preview
        with Vertical(id="bottom-container"):
            self.browser_panel = BrowserPreviewPanel(classes="panel-container")
            yield self.browser_panel

        yield Footer()

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Initialize metrics
        self.update_metrics()

        # Start orchestrator as background worker if provided
        if self.orchestrator:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("=== STARTING ORCHESTRATOR AS WORKER ===")
            self.run_worker(self._run_orchestrator(), exclusive=False)

    async def _run_orchestrator(self):
        """Run the orchestrator and handle completion."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            logger.info("=== WORKER: Starting orchestrator.run() ===")
            await self.orchestrator.run()
            logger.info("=== WORKER: Orchestrator completed successfully ===")

            # Keep app alive for a few seconds after completion
            import asyncio
            logger.info("Keeping app alive for 5 seconds...")
            await asyncio.sleep(5)

            logger.info("Calling self.exit()...")
            self.exit()

        except Exception as e:
            logger.exception("=== WORKER: Orchestrator failed ===")
            self.notify(f"Orchestrator failed: {e}", title="Error", severity="error", timeout=10)
            import traceback
            traceback.print_exc()
            # Keep app alive for 10 seconds to show error
            import asyncio
            await asyncio.sleep(10)
            self.exit()

    def update_metrics(self):
        """Update metrics panel."""
        if not self.metrics_panel:
            return

        completed = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.FAILED)
        skipped = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.SKIPPED)

        # Calculate average time
        completed_tasks = [t for t in self.task_list.tasks if t.status == TaskStatus.COMPLETED]
        avg_time = 0.0
        total_time = 0.0

        if completed_tasks:
            for task in completed_tasks:
                if task.started_at and task.completed_at:
                    duration = (task.completed_at - task.started_at).total_seconds()
                    total_time += duration

            avg_time = total_time / len(completed_tasks) if completed_tasks else 0.0

        self.metrics_panel.update_metrics(
            total=len(self.task_list),
            completed=completed,
            failed=failed,
            skipped=skipped,
            avg_time=avg_time,
            total_time=total_time,
        )

    def update_task_queue(self, current_task_id: Optional[str] = None):
        """Update task queue display."""
        if self.task_queue_panel:
            self.task_queue_panel.update_tasks(self.task_list, current_task_id)
        self.update_metrics()

    def update_execution(
        self,
        task: Optional[Task] = None,
        progress: float = 0.0,
        elapsed: float = 0.0,
        retries: int = 0,
    ):
        """Update execution panel."""
        if self.execution_panel:
            self.execution_panel.update_execution(task, progress, elapsed, retries)

    def update_browser(self, url: str = "", branch: str = "", preview: str = ""):
        """Update browser preview."""
        if self.browser_panel:
            self.browser_panel.update_preview(url, branch, preview)

    # Action handlers
    def action_peek(self):
        """Peek at browser."""
        self.notify("Taking browser screenshot...", title="Peek")

    def action_create_pr(self):
        """Create PR."""
        self.notify("Creating pull request...", title="Create PR")

    def action_skip(self):
        """Skip current task."""
        self.notify("Skipping current task...", title="Skip", severity="warning")

    def action_retry(self):
        """Retry current task."""
        self.notify("Retrying current task...", title="Retry")

    def action_abort(self):
        """Abort execution."""
        self.notify("Aborting execution...", title="Abort", severity="error")

    def action_help(self):
        """Show help."""
        help_text = """
        Keyboard Shortcuts:

        q     - Quit application
        p     - Peek at browser
        c     - Create pull request
        s     - Skip current task
        r     - Retry current task
        a     - Abort execution
        ?     - Show this help
        ↑/k   - Scroll up
        ↓/j   - Scroll down
        """
        self.notify(help_text, title="Help", timeout=10)

    def action_scroll_up(self):
        """Scroll up."""
        pass

    def action_scroll_down(self):
        """Scroll down."""
        pass


if __name__ == "__main__":
    # Demo the TUI
    from conductor.tasks.models import Task, TaskStatus, Priority

    tasks = [
        Task(
            id="AUTH-001",
            name="Add Auth Tests",
            prompt="Create unit tests",
            expected_deliverable="test_auth.py",
            priority=Priority.HIGH,
            status=TaskStatus.COMPLETED,
        ),
        Task(
            id="DOC-001",
            name="Update Documentation",
            prompt="Update docs",
            expected_deliverable="Updated docs",
            priority=Priority.MEDIUM,
            status=TaskStatus.RUNNING,
        ),
        Task(
            id="REFACTOR-001",
            name="Refactor Auth Module",
            prompt="Refactor code",
            expected_deliverable="Refactored auth",
            priority=Priority.LOW,
            status=TaskStatus.PENDING,
        ),
    ]

    task_list = TaskList(tasks=tasks)
    app = ConductorTUI(task_list=task_list)
    app.run()
