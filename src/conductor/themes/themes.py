"""
Theme definitions for Conductor.
Implements Story 3.4: Theme System
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Theme:
    """TUI theme colors and styles."""

    name: str
    primary: str
    secondary: str
    success: str
    warning: str
    error: str
    background: str
    surface: str
    panel_border: str
    text_primary: str
    text_secondary: str

    # Panel-specific colors
    task_queue_border: str = "cyan"
    execution_border: str = "yellow"
    metrics_border: str = "green"
    browser_border: str = "magenta"


# Default theme - clean and professional
DEFAULT_THEME = Theme(
    name="default",
    primary="cyan",
    secondary="blue",
    success="green",
    warning="yellow",
    error="red",
    background="$background",
    surface="$surface",
    panel_border="bright_cyan",
    text_primary="white",
    text_secondary="bright_black",
    task_queue_border="cyan",
    execution_border="yellow",
    metrics_border="green",
    browser_border="magenta",
)

# Cyberpunk theme - neon colors
CYBERPUNK_THEME = Theme(
    name="cyberpunk",
    primary="magenta",
    secondary="cyan",
    success="#00ff00",
    warning="#ffff00",
    error="#ff00ff",
    background="#0a0a0a",
    surface="#1a1a2e",
    panel_border="bright_magenta",
    text_primary="#00ffff",
    text_secondary="#ff00ff",
    task_queue_border="bright_magenta",
    execution_border="bright_cyan",
    metrics_border="bright_green",
    browser_border="bright_yellow",
)

# Minimal theme - subdued colors
MINIMAL_THEME = Theme(
    name="minimal",
    primary="white",
    secondary="bright_black",
    success="green",
    warning="yellow",
    error="red",
    background="$background",
    surface="$surface",
    panel_border="white",
    text_primary="white",
    text_secondary="bright_black",
    task_queue_border="white",
    execution_border="white",
    metrics_border="white",
    browser_border="white",
)

# Solarized Dark theme
SOLARIZED_DARK_THEME = Theme(
    name="solarized-dark",
    primary="#268bd2",
    secondary="#2aa198",
    success="#859900",
    warning="#b58900",
    error="#dc322f",
    background="#002b36",
    surface="#073642",
    panel_border="#586e75",
    text_primary="#839496",
    text_secondary="#657b83",
    task_queue_border="#268bd2",
    execution_border="#b58900",
    metrics_border="#859900",
    browser_border="#6c71c4",
)

# Dracula theme
DRACULA_THEME = Theme(
    name="dracula",
    primary="#bd93f9",
    secondary="#8be9fd",
    success="#50fa7b",
    warning="#f1fa8c",
    error="#ff5555",
    background="#282a36",
    surface="#44475a",
    panel_border="#6272a4",
    text_primary="#f8f8f2",
    text_secondary="#6272a4",
    task_queue_border="#bd93f9",
    execution_border="#ffb86c",
    metrics_border="#50fa7b",
    browser_border="#ff79c6",
)


class ThemeManager:
    """Manages available themes."""

    def __init__(self):
        self._themes: Dict[str, Theme] = {
            "default": DEFAULT_THEME,
            "cyberpunk": CYBERPUNK_THEME,
            "minimal": MINIMAL_THEME,
            "solarized-dark": SOLARIZED_DARK_THEME,
            "dracula": DRACULA_THEME,
        }
        self._current_theme = "default"

    def get_theme(self, name: str) -> Optional[Theme]:
        """Get theme by name."""
        return self._themes.get(name)

    def set_current_theme(self, name: str) -> bool:
        """Set current theme."""
        if name in self._themes:
            self._current_theme = name
            return True
        return False

    def get_current_theme(self) -> Theme:
        """Get current theme."""
        return self._themes[self._current_theme]

    def list_themes(self) -> list[str]:
        """List all available themes."""
        return list(self._themes.keys())

    def add_theme(self, theme: Theme) -> None:
        """Add a custom theme."""
        self._themes[theme.name] = theme

    def generate_textual_css(self, theme: Theme) -> str:
        """
        Generate Textual CSS from theme.

        Args:
            theme: Theme to generate CSS for

        Returns:
            CSS string
        """
        return f"""
        Screen {{
            background: {theme.background};
        }}

        .success {{
            color: {theme.success};
        }}

        .warning {{
            color: {theme.warning};
        }}

        .error {{
            color: {theme.error};
        }}

        TaskQueuePanel {{
            border: solid {theme.task_queue_border};
        }}

        ExecutionPanel {{
            border: solid {theme.execution_border};
        }}

        MetricsPanel {{
            border: solid {theme.metrics_border};
        }}

        BrowserPreviewPanel {{
            border: solid {theme.browser_border};
        }}
        """


# Global theme manager instance
_theme_manager = ThemeManager()


def get_theme(name: str = "default") -> Theme:
    """
    Get a theme by name.

    Args:
        name: Theme name

    Returns:
        Theme object
    """
    theme = _theme_manager.get_theme(name)
    return theme if theme else DEFAULT_THEME


def get_theme_manager() -> ThemeManager:
    """Get the global theme manager."""
    return _theme_manager
