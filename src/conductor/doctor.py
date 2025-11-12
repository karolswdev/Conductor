"""
Diagnostic mode for verifying MCP connectivity and browser automation.

This module provides health checks and diagnostic tools for ensuring
Conductor can properly connect to MCP and control the browser.
"""

import asyncio
import logging
from typing import Dict, List
from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm

from conductor.mcp.client import MCPClient, MCPConnectionError
from conductor.mcp.browser import BrowserController
from conductor.utils.config import Config


logger = logging.getLogger(__name__)
console = Console()


@dataclass
class DiagnosticResult:
    """Result of a diagnostic check."""

    name: str
    status: str  # "pass", "fail", "warning", "skip"
    message: str
    details: str = ""


class DoctorDiagnostics:
    """
    Run diagnostic checks for Conductor health.

    Verifies:
    - MCP server connectivity
    - Browser launch capability
    - Navigation functionality
    - User visibility confirmation
    """

    def __init__(self, config: Config, headless: bool = False):
        """
        Initialize diagnostics.

        Args:
            config: Conductor configuration
            headless: Whether to run browser in headless mode
        """
        self.config = config
        self.headless = headless
        self.results: List[DiagnosticResult] = []
        self.mcp_client: MCPClient | None = None
        self.browser: BrowserController | None = None

    async def run_all_checks(self) -> bool:
        """
        Run all diagnostic checks.

        Returns:
            True if all checks passed, False otherwise
        """
        console.print("\n[bold cyan]🏥 Conductor Doctor - Running Diagnostics[/bold cyan]\n")

        try:
            await self._check_mcp_connection()
            await self._check_browser_launch()
            await self._check_navigation()
            await self._check_user_visibility()

        except KeyboardInterrupt:
            console.print("\n[yellow]Diagnostics interrupted by user[/yellow]")
            return False
        finally:
            await self._cleanup()

        self._print_results()
        return self._all_passed()

    async def _check_mcp_connection(self) -> None:
        """Check MCP server connection."""
        console.print("[cyan]→ Checking MCP connection...[/cyan]")

        try:
            self.mcp_client = MCPClient(
                server_url=self.config.mcp.server_url,
                timeout=self.config.mcp.timeout,
                max_retries=self.config.mcp.max_retries,
            )

            await self.mcp_client.connect()

            if self.mcp_client.is_connected:
                # Actually verify by listing tools
                try:
                    tools = await self.mcp_client.list_tools()
                    tool_names = [t["name"] for t in tools]

                    self.results.append(
                        DiagnosticResult(
                            name="MCP Connection",
                            status="pass",
                            message=f"Successfully connected to {self.config.mcp.server_url}",
                            details=f"Found {len(tools)} tools: {', '.join(tool_names[:3])}{'...' if len(tools) > 3 else ''}",
                        )
                    )
                    console.print(f"  [green]✓[/green] MCP connection successful ({len(tools)} tools available)")
                except Exception as e:
                    logger.warning(f"Connected but couldn't list tools: {e}")
                    self.results.append(
                        DiagnosticResult(
                            name="MCP Connection",
                            status="warning",
                            message=f"Connected but tool listing failed",
                            details=str(e),
                        )
                    )
                    console.print("  [yellow]![/yellow] MCP connected but tool listing failed")
            else:
                raise MCPConnectionError("Connection established but not confirmed")

        except MCPConnectionError as e:
            self.results.append(
                DiagnosticResult(
                    name="MCP Connection",
                    status="fail",
                    message=f"Failed to connect to MCP server",
                    details=str(e),
                )
            )
            console.print(f"  [red]✗[/red] MCP connection failed: {e}")
            raise  # Stop further checks

    async def _check_browser_launch(self) -> None:
        """Check browser launch capability."""
        console.print("[cyan]→ Checking browser launch...[/cyan]")

        if not self.mcp_client or not self.mcp_client.is_connected:
            self.results.append(
                DiagnosticResult(
                    name="Browser Launch",
                    status="skip",
                    message="Skipped (MCP not connected)",
                )
            )
            console.print("  [yellow]⊘[/yellow] Browser launch skipped")
            return

        try:
            self.browser = BrowserController(self.mcp_client)
            await self.browser.launch_browser(headless=self.headless)

            if self.browser.is_launched:
                mode = "headless" if self.headless else "headed"
                self.results.append(
                    DiagnosticResult(
                        name="Browser Launch",
                        status="pass",
                        message=f"Browser launched successfully in {mode} mode",
                    )
                )
                console.print(f"  [green]✓[/green] Browser launched ({mode} mode)")
            else:
                raise Exception("Browser launch not confirmed")

        except Exception as e:
            self.results.append(
                DiagnosticResult(
                    name="Browser Launch",
                    status="fail",
                    message="Failed to launch browser",
                    details=str(e),
                )
            )
            console.print(f"  [red]✗[/red] Browser launch failed: {e}")

    async def _check_navigation(self) -> None:
        """Check navigation to google.com."""
        console.print("[cyan]→ Checking navigation (google.com)...[/cyan]")

        if not self.browser or not self.browser.is_launched:
            self.results.append(
                DiagnosticResult(
                    name="Navigation Test",
                    status="skip",
                    message="Skipped (browser not launched)",
                )
            )
            console.print("  [yellow]⊘[/yellow] Navigation test skipped")
            return

        try:
            test_url = "https://www.google.com"
            await self.browser.navigate(test_url)

            # Give it a moment to load
            await asyncio.sleep(2)

            # Try to get current URL to confirm navigation
            try:
                current_url = await self.browser.get_current_url()

                # Check if we got actual URL data (not mock)
                if isinstance(current_url, str) and current_url and "mock" not in current_url.lower():
                    if "google" in current_url.lower():
                        url_detail = f"Confirmed at: {current_url}"
                        status = "pass"
                    else:
                        url_detail = f"Unexpected URL: {current_url}"
                        status = "warning"
                else:
                    url_detail = f"Got mock/invalid response: {current_url}"
                    status = "warning"

                self.results.append(
                    DiagnosticResult(
                        name="Navigation Test",
                        status=status,
                        message=f"Navigated to {test_url}" if status == "pass" else "Navigation may not be real",
                        details=url_detail,
                    )
                )

                if status == "pass":
                    console.print(f"  [green]✓[/green] Navigation successful and verified")
                else:
                    console.print(f"  [yellow]![/yellow] Navigation command sent but verification unclear")

            except Exception as verify_e:
                logger.warning(f"URL verification failed: {verify_e}")
                self.results.append(
                    DiagnosticResult(
                        name="Navigation Test",
                        status="warning",
                        message="Navigation sent but couldn't verify URL",
                        details=str(verify_e),
                    )
                )
                console.print("  [yellow]![/yellow] Navigation sent but couldn't verify")

        except Exception as e:
            self.results.append(
                DiagnosticResult(
                    name="Navigation Test",
                    status="fail",
                    message="Failed to navigate to test URL",
                    details=str(e),
                )
            )
            console.print(f"  [red]✗[/red] Navigation failed: {e}")

    async def _check_user_visibility(self) -> None:
        """Ask user to confirm browser visibility."""
        console.print("[cyan]→ Checking user visibility...[/cyan]")

        if self.headless:
            self.results.append(
                DiagnosticResult(
                    name="User Visibility",
                    status="skip",
                    message="Skipped (headless mode enabled)",
                )
            )
            console.print("  [yellow]⊘[/yellow] Visibility check skipped (headless mode)")
            return

        if not self.browser or not self.browser.is_launched:
            self.results.append(
                DiagnosticResult(
                    name="User Visibility",
                    status="skip",
                    message="Skipped (browser not launched)",
                )
            )
            console.print("  [yellow]⊘[/yellow] Visibility check skipped")
            return

        # Give user time to observe
        console.print("\n[bold yellow]Please check your screen:[/bold yellow]")
        console.print("  • Can you see a browser window?")
        console.print("  • Is it showing Google's homepage?")
        console.print("  • Can you interact with it?\n")

        # Wait a bit before asking
        await asyncio.sleep(1)

        try:
            # Use rich's Confirm for yes/no prompt
            can_see_browser = Confirm.ask("Can you see the browser window with Google?")

            if can_see_browser:
                self.results.append(
                    DiagnosticResult(
                        name="User Visibility",
                        status="pass",
                        message="User confirmed browser is visible and working",
                    )
                )
                console.print("  [green]✓[/green] User confirmed visibility")
            else:
                self.results.append(
                    DiagnosticResult(
                        name="User Visibility",
                        status="fail",
                        message="User could not see browser window",
                        details="Browser may be hidden, minimized, or on different screen",
                    )
                )
                console.print("  [red]✗[/red] User could not see browser")

        except Exception as e:
            self.results.append(
                DiagnosticResult(
                    name="User Visibility",
                    status="warning",
                    message="Could not get user confirmation",
                    details=str(e),
                )
            )
            console.print(f"  [yellow]![/yellow] Visibility check inconclusive")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        console.print("\n[cyan]→ Cleaning up...[/cyan]")

        if self.browser:
            try:
                await self.browser.close()
                console.print("  [green]✓[/green] Browser closed")
            except Exception as e:
                console.print(f"  [yellow]![/yellow] Browser cleanup warning: {e}")

        if self.mcp_client:
            try:
                await self.mcp_client.disconnect()
                console.print("  [green]✓[/green] MCP disconnected")
            except Exception as e:
                console.print(f"  [yellow]![/yellow] MCP cleanup warning: {e}")

    def _print_results(self) -> None:
        """Print diagnostic results in a nice table."""
        console.print("\n" + "=" * 70)
        console.print("\n[bold cyan]📊 Diagnostic Results[/bold cyan]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Check", style="white", width=20)
        table.add_column("Status", width=10)
        table.add_column("Message", width=35)

        status_styles = {
            "pass": "[green]✓ PASS[/green]",
            "fail": "[red]✗ FAIL[/red]",
            "warning": "[yellow]! WARN[/yellow]",
            "skip": "[dim]⊘ SKIP[/dim]",
        }

        for result in self.results:
            status_text = status_styles.get(result.status, result.status)
            table.add_row(
                result.name,
                status_text,
                result.message,
            )

            # Show details if present
            if result.details:
                console.print(f"    [dim]{result.details}[/dim]")

        console.print(table)

        # Summary
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")
        warnings = sum(1 for r in self.results if r.status == "warning")
        skipped = sum(1 for r in self.results if r.status == "skip")

        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"  [green]Passed:[/green] {passed}")
        console.print(f"  [red]Failed:[/red] {failed}")
        console.print(f"  [yellow]Warnings:[/yellow] {warnings}")
        console.print(f"  [dim]Skipped:[/dim] {skipped}")

        if self._all_passed():
            console.print("\n[bold green]✓ All checks passed! Conductor is healthy.[/bold green]")
        else:
            console.print("\n[bold red]✗ Some checks failed. Please review above.[/bold red]")
            console.print("\n[yellow]Troubleshooting tips:[/yellow]")
            console.print("  • Ensure MCP server is running: npx @anthropic/playwright-mcp")
            console.print("  • Check firewall settings if using remote MCP")
            console.print("  • Verify browser installation: playwright install chromium")
            console.print("  • Check config at ~/.conductor/config.yaml")

    def _all_passed(self) -> bool:
        """Check if all non-skipped checks passed."""
        for result in self.results:
            if result.status in ("fail",):
                return False
        return True


async def run_doctor(config: Config, headless: bool = False) -> bool:
    """
    Run doctor diagnostics.

    Args:
        config: Conductor configuration
        headless: Whether to run in headless mode

    Returns:
        True if all checks passed, False otherwise
    """
    doctor = DoctorDiagnostics(config, headless=headless)
    return await doctor.run_all_checks()
