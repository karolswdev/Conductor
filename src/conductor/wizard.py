"""
Interactive configuration wizard.
Implements Story 8.1: Configuration Wizard
"""

import asyncio
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich import box

from conductor.utils.config import Config, MCPConfig, AuthConfig, RetryConfig, UIConfig
from conductor.themes.themes import get_theme_manager


console = Console()


class ConfigurationWizard:
    """
    Interactive TUI-based configuration wizard.

    Guides users through setting up Conductor with:
    - MCP server configuration
    - Authentication settings
    - Retry policies
    - UI preferences
    - Theme selection
    """

    def __init__(self):
        self.config = Config()

    async def run(self) -> Config:
        """
        Run the configuration wizard.

        Returns:
            Configured Config object
        """
        console.clear()

        # Show welcome
        self._show_welcome()

        # Configure sections
        await self._configure_mcp()
        await self._configure_auth()
        await self._configure_retry()
        await self._configure_ui()

        # Show summary and confirm
        if self._show_summary():
            return self.config
        else:
            console.print("[yellow]Configuration cancelled[/yellow]")
            return Config()  # Return default

    def _show_welcome(self):
        """Show welcome message."""
        welcome = Panel(
            """
[bold cyan]Welcome to Conductor Configuration Wizard![/bold cyan]

This wizard will help you set up Conductor for optimal performance.

We'll configure:
  • MCP server connection
  • Authentication settings
  • Retry policies
  • UI preferences
  • Theme selection

Press Ctrl+C at any time to cancel.
            """,
            title="🎭 Conductor Setup",
            border_style="cyan",
            box=box.DOUBLE,
        )
        console.print(welcome)
        console.print()

    async def _configure_mcp(self):
        """Configure MCP settings."""
        console.print("[bold cyan]MCP Server Configuration[/bold cyan]\n")

        server_url = Prompt.ask(
            "MCP server URL",
            default=self.config.mcp.server_url,
        )

        timeout = float(
            Prompt.ask(
                "Connection timeout (seconds)",
                default=str(self.config.mcp.timeout),
            )
        )

        max_retries = int(
            Prompt.ask(
                "Maximum connection retries",
                default=str(self.config.mcp.max_retries),
            )
        )

        self.config.mcp = MCPConfig(
            server_url=server_url, timeout=timeout, max_retries=max_retries
        )

        console.print("[green]✓[/green] MCP configuration complete\n")

    async def _configure_auth(self):
        """Configure authentication settings."""
        console.print("[bold yellow]Authentication Configuration[/bold yellow]\n")

        timeout = int(
            Prompt.ask(
                "Authentication timeout (seconds)",
                default=str(self.config.auth.timeout),
            )
        )

        check_interval = float(
            Prompt.ask(
                "Login check interval (seconds)",
                default=str(self.config.auth.check_interval),
            )
        )

        headless = Confirm.ask(
            "Run browser in headless mode?", default=self.config.auth.headless
        )

        self.config.auth = AuthConfig(
            timeout=timeout, check_interval=check_interval, headless=headless
        )

        console.print("[green]✓[/green] Authentication configuration complete\n")

    async def _configure_retry(self):
        """Configure retry settings."""
        console.print("[bold magenta]Retry Policy Configuration[/bold magenta]\n")

        max_attempts = int(
            Prompt.ask(
                "Maximum retry attempts",
                default=str(self.config.retry.max_attempts),
            )
        )

        initial_delay = float(
            Prompt.ask(
                "Initial retry delay (seconds)",
                default=str(self.config.retry.initial_delay),
            )
        )

        backoff_factor = float(
            Prompt.ask(
                "Backoff multiplier",
                default=str(self.config.retry.backoff_factor),
            )
        )

        max_delay = float(
            Prompt.ask(
                "Maximum retry delay (seconds)",
                default=str(self.config.retry.max_delay),
            )
        )

        jitter = float(
            Prompt.ask(
                "Jitter percentage (0.0-0.5)",
                default=str(self.config.retry.jitter),
            )
        )

        self.config.retry = RetryConfig(
            max_attempts=max_attempts,
            initial_delay=initial_delay,
            backoff_factor=backoff_factor,
            max_delay=max_delay,
            jitter=jitter,
        )

        console.print("[green]✓[/green] Retry policy configuration complete\n")

    async def _configure_ui(self):
        """Configure UI settings."""
        console.print("[bold green]UI Configuration[/bold green]\n")

        # Show available themes
        theme_manager = get_theme_manager()
        themes = theme_manager.list_themes()

        table = Table(title="Available Themes", box=box.ROUNDED)
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="white")

        theme_descriptions = {
            "default": "Clean and professional",
            "cyberpunk": "Neon colors and retro-futuristic",
            "minimal": "Subdued and distraction-free",
            "solarized-dark": "Eye-friendly solarized palette",
            "dracula": "Popular dark theme with purple accents",
        }

        for theme_name in themes:
            desc = theme_descriptions.get(theme_name, "")
            table.add_row(theme_name, desc)

        console.print(table)
        console.print()

        theme = Prompt.ask(
            "Select theme",
            choices=themes,
            default=self.config.ui.theme,
        )

        refresh_rate = int(
            Prompt.ask(
                "UI refresh rate (FPS)",
                default=str(self.config.ui.refresh_rate),
            )
        )

        show_splash = Confirm.ask(
            "Show splash screen on startup?", default=self.config.ui.show_splash
        )

        self.config.ui = UIConfig(
            theme=theme,
            refresh_rate=refresh_rate,
            show_splash=show_splash,
        )

        console.print(f"[green]✓[/green] UI configuration complete\n")

    def _show_summary(self) -> bool:
        """
        Show configuration summary and confirm.

        Returns:
            True if user confirms, False otherwise
        """
        console.print("\n[bold]Configuration Summary[/bold]\n")

        summary = Table(box=box.ROUNDED)
        summary.add_column("Setting", style="cyan", width=30)
        summary.add_column("Value", style="white", width=40)

        # MCP settings
        summary.add_row("[bold]MCP Server[/bold]", "")
        summary.add_row("  Server URL", self.config.mcp.server_url)
        summary.add_row("  Timeout", f"{self.config.mcp.timeout}s")
        summary.add_row("  Max Retries", str(self.config.mcp.max_retries))

        # Auth settings
        summary.add_row("[bold]Authentication[/bold]", "")
        summary.add_row("  Timeout", f"{self.config.auth.timeout}s")
        summary.add_row("  Check Interval", f"{self.config.auth.check_interval}s")
        summary.add_row("  Headless", str(self.config.auth.headless))

        # Retry settings
        summary.add_row("[bold]Retry Policy[/bold]", "")
        summary.add_row("  Max Attempts", str(self.config.retry.max_attempts))
        summary.add_row("  Initial Delay", f"{self.config.retry.initial_delay}s")
        summary.add_row("  Backoff Factor", str(self.config.retry.backoff_factor))
        summary.add_row("  Jitter", f"{self.config.retry.jitter * 100}%")

        # UI settings
        summary.add_row("[bold]UI[/bold]", "")
        summary.add_row("  Theme", self.config.ui.theme)
        summary.add_row("  Refresh Rate", f"{self.config.ui.refresh_rate} FPS")
        summary.add_row("  Show Splash", str(self.config.ui.show_splash))

        console.print(summary)
        console.print()

        return Confirm.ask("Save this configuration?", default=True)


def run_wizard() -> Config:
    """
    Run the configuration wizard synchronously.

    Returns:
        Configured Config object
    """
    wizard = ConfigurationWizard()
    return asyncio.run(wizard.run())
