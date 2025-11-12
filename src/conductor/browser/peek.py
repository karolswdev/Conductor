"""
Browser peeking functionality - view browser state as ASCII art.
Implements Story 5.1: Browser Peek
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from PIL import Image
import io

from ..mcp.browser import BrowserController


logger = logging.getLogger(__name__)


class BrowserPeek:
    """
    Provides browser peeking functionality.

    Features:
    - Screenshot capture
    - ASCII art conversion
    - URL and branch extraction
    - Automatic updates
    """

    def __init__(self, browser: BrowserController, update_interval: float = 10.0):
        """
        Initialize browser peek.

        Args:
            browser: Browser controller
            update_interval: How often to update (seconds)
        """
        self.browser = browser
        self.update_interval = update_interval
        self._running = False
        self._update_task = None

    async def capture_screenshot(self, output_path: Optional[Path] = None) -> bytes:
        """
        Capture browser screenshot.

        Args:
            output_path: Optional path to save screenshot

        Returns:
            Screenshot bytes
        """
        return await self.browser.screenshot(output_path)

    def screenshot_to_ascii(
        self, screenshot_bytes: bytes, width: int = 80, height: int = 24
    ) -> str:
        """
        Convert screenshot to ASCII art.

        Args:
            screenshot_bytes: Screenshot data
            width: ASCII art width
            height: ASCII art height

        Returns:
            ASCII art string
        """
        try:
            # Load image
            image = Image.open(io.BytesIO(screenshot_bytes))

            # Resize to target dimensions
            image = image.resize((width, height))

            # Convert to grayscale
            image = image.convert("L")

            # ASCII characters from dark to light
            ascii_chars = " .:-=+*#%@"

            # Convert pixels to ASCII
            pixels = image.getdata()
            ascii_str = ""

            for i, pixel in enumerate(pixels):
                # Map pixel value (0-255) to ASCII char
                char_index = pixel * len(ascii_chars) // 256
                ascii_str += ascii_chars[char_index]

                # Add newline at end of row
                if (i + 1) % width == 0:
                    ascii_str += "\n"

            return ascii_str

        except Exception as e:
            logger.error(f"Failed to convert screenshot to ASCII: {e}")
            return "[Preview unavailable]"

    async def get_current_state(self) -> dict:
        """
        Get current browser state.

        Returns:
            Dictionary with url, branch, and preview
        """
        try:
            url = await self.browser.get_current_url()

            # Extract branch from URL or page
            # Simplified - would need actual implementation
            branch = ""
            if "/code/" in url:
                # Try to extract session/branch info
                session_part = url.split("/code/")[1].split("?")[0]
                branch = f"claude/{session_part[:8]}"

            # Capture and convert screenshot
            screenshot = await self.capture_screenshot()
            preview = self.screenshot_to_ascii(screenshot, width=60, height=20)

            return {"url": url, "branch": branch, "preview": preview}

        except Exception as e:
            logger.error(f"Failed to get browser state: {e}")
            return {"url": "", "branch": "", "preview": "[Error capturing preview]"}

    async def start_auto_update(self, update_callback):
        """
        Start automatic browser state updates.

        Args:
            update_callback: Async function to call with state updates
        """
        self._running = True

        async def update_loop():
            while self._running:
                try:
                    state = await self.get_current_state()
                    await update_callback(state)
                except Exception as e:
                    logger.error(f"Update failed: {e}")

                await asyncio.sleep(self.update_interval)

        self._update_task = asyncio.create_task(update_loop())

    def stop_auto_update(self):
        """Stop automatic updates."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
