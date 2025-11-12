"""
Main entry point for Conductor CLI.
"""

import click
import asyncio
import logging
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler

from conductor import __version__
from conductor.tui.splash import show_splash
from conductor.tasks.loader import TaskLoader, TaskLoadError
from conductor.utils.config import load_config
from conductor.orchestrator import Orchestrator


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_time=False)],
)

logger = logging.getLogger(__name__)
console = Console()


@click.group()
@click.version_option(version=__version__)
def cli():
    """
    🎭 Conductor - Claude Code Orchestration Suite

    Orchestrating intelligence, one task at a time.
    """
    pass


@cli.command()
@click.argument("tasks_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),
    help="Path to configuration file",
)
@click.option(
    "--theme",
    "-t",
    default="default",
    help="UI theme to use",
)
@click.option(
    "--repo",
    "-r",
    help="Repository to use (overrides config)",
)
@click.option(
    "--no-splash",
    is_flag=True,
    help="Skip splash screen",
)
@click.option(
    "--headless",
    is_flag=True,
    help="Run browser in headless mode",
)
@click.option(
    "--no-tui",
    is_flag=True,
    help="Disable TUI (use simple console mode)",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
def run(
    tasks_file: Path,
    config: Path | None,
    theme: str,
    repo: str | None,
    no_splash: bool,
    headless: bool,
    no_tui: bool,
    debug: bool,
):
    """
    Run tasks from a YAML file.

    TASKS_FILE: Path to YAML file containing task definitions
    """
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load configuration
        cfg = load_config(config)

        # Override config with CLI options
        if theme:
            cfg.ui.theme = theme
        if no_splash:
            cfg.ui.show_splash = False
        if headless:
            cfg.auth.headless = True
        if repo:
            cfg.default_repository = repo

        # Show splash screen (only if not using TUI)
        if cfg.ui.show_splash and no_tui:
            show_splash(console, duration=cfg.ui.splash_duration)

        # Load tasks
        console.print(f"\n[cyan]Loading tasks from {tasks_file}...[/cyan]")
        task_list = TaskLoader.load_from_file(tasks_file)
        console.print(f"[green]✓[/green] Loaded {len(task_list)} tasks\n")

        # Run orchestrator
        if no_tui:
            # Use simple console orchestrator
            asyncio.run(run_orchestrator_simple(cfg, task_list))
        else:
            # Use TUI orchestrator
            asyncio.run(run_orchestrator_tui(cfg, task_list))

    except TaskLoadError as e:
        console.print(f"[red]Error loading tasks:[/red] {e}")
        raise click.Abort()

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        raise click.Abort()

    except Exception as e:
        logger.exception("Unexpected error")
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


async def run_orchestrator_simple(config, task_list):
    """Run the simple console orchestrator."""
    orchestrator = Orchestrator(config, task_list)
    await orchestrator.run()


async def run_orchestrator_tui(config, task_list):
    """Run the TUI orchestrator."""
    from conductor.orchestrator_tui import run_with_tui

    await run_with_tui(config, task_list)


@cli.command()
@click.argument("tasks_file", type=click.Path(exists=True, path_type=Path))
def validate(tasks_file: Path):
    """
    Validate a tasks YAML file.

    TASKS_FILE: Path to YAML file to validate
    """
    try:
        console.print(f"[cyan]Validating {tasks_file}...[/cyan]")

        task_list = TaskLoader.load_from_file(tasks_file)

        console.print(f"[green]✓ Valid![/green]\n")
        console.print(f"  Total tasks: {len(task_list)}")

        # Show task summary
        console.print("\n[bold]Tasks:[/bold]")
        for task in task_list.tasks:
            deps = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
            console.print(f"  • {task.id}: {task.name}{deps}")

    except TaskLoadError as e:
        console.print(f"[red]✗ Validation failed:[/red]\n{e}")
        raise click.Abort()


@cli.command()
@click.option(
    "--wizard",
    "-w",
    is_flag=True,
    help="Use interactive configuration wizard",
)
def init(wizard: bool):
    """
    Initialize Conductor configuration.

    Creates a default configuration file at ~/.conductor/config.yaml
    """
    config_path = Path.home() / ".conductor" / "config.yaml"

    if config_path.exists():
        if not click.confirm(f"Config file already exists at {config_path}. Overwrite?"):
            console.print("[yellow]Initialization cancelled[/yellow]")
            return

    # Use wizard or create default
    if wizard:
        from conductor.wizard import run_wizard

        console.print("[cyan]Starting configuration wizard...[/cyan]\n")
        config = run_wizard()
    else:
        from conductor.utils.config import Config

        config = Config()

    config.to_file(config_path)

    console.print(f"\n[green]✓[/green] Configuration created at {config_path}")
    console.print("\nYou can now:")
    console.print("  1. Edit the config file to customize settings")
    console.print("  2. Create a tasks.yaml file with your tasks")
    console.print("  3. Run: [cyan]conductor run tasks.yaml[/cyan]")


@cli.command()
def version():
    """Show version information."""
    console.print(f"[bold cyan]Conductor[/bold cyan] version [bold]{__version__}[/bold]")
    console.print("\n[italic]Orchestrating intelligence, one task at a time[/italic]")


if __name__ == "__main__":
    cli()
