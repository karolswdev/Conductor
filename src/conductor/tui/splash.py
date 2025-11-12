"""
Splash screen for Conductor with beautiful ASCII art.
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich import box
import time
from typing import Optional


CONDUCTOR_ASCII = r"""
   ╔═══════════════════════════════════════════════════╗
   ║     ╭─╮                   ╭╮                      ║
   ║    ╱  ╰─╮   ╭─╮  ╭─╮ ╭─╮  │╰╮  ╭╮  ╭─╮ ╭─╮  ╭─╮  ║
   ║   │      │  │ │  │ │ │ │  │ │  │╰─╮│  ╰─╯│ │ ║  ║
   ║   │      │  │ │  │ │ │ │  │ │  │  ││   ╭─╯ │ ║  ║
   ║    ╰─────╯  ╰─╯  ╰─╯ ╰─╯  ╰─╯  ╰──╯╰   ╰─── ╰─╯  ║
   ║                                                    ║
   ║           O R C H E S T R A T O R                 ║
   ╚═══════════════════════════════════════════════════╝
"""


def create_splash_text(version: str = "0.1.0") -> Text:
    """Create the splash screen text with styling."""
    text = Text()

    # ASCII art with gradient effect
    lines = CONDUCTOR_ASCII.split('\n')
    for i, line in enumerate(lines):
        # Create a gradient from cyan to blue
        color = f"rgb({0},{int(255 - i * 10)},{255})"
        text.append(line + "\n", style=color)

    return text


def show_splash(console: Optional[Console] = None, duration: float = 2.0) -> None:
    """
    Display the splash screen with animation.

    Args:
        console: Rich console instance. If None, creates a new one.
        duration: How long to display the splash screen in seconds.
    """
    if console is None:
        console = Console()

    console.clear()

    # Create splash content
    splash_text = create_splash_text()

    # Add subtitle
    subtitle = Text("\n\"Orchestrating intelligence, one task at a time\"\n", style="italic cyan")

    # Add version info
    from conductor import __version__
    version_text = Text(f"\nVersion {__version__}", style="dim white")

    # Add credits
    credits = Text("\nby karolswdev", style="dim white")

    # Combine all text
    full_text = Text()
    full_text.append(splash_text)
    full_text.append(subtitle)
    full_text.append(version_text)
    full_text.append(credits)

    # Create panel with the splash
    panel = Panel(
        Align.center(full_text),
        box=box.DOUBLE,
        border_style="bright_cyan",
        padding=(1, 2),
    )

    # Display with animation
    console.print(panel)

    # Loading animation
    loading_text = Text("\nInitializing", style="cyan")
    for i in range(3):
        console.print(Align.center(loading_text + "." * (i + 1)), end="\r")
        time.sleep(duration / 4)

    console.print()  # New line after loading


if __name__ == "__main__":
    # Demo the splash screen
    show_splash()
