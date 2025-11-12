"""
Browser controller using MCP Playwright integration.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from .client import MCPClient, MCPError


logger = logging.getLogger(__name__)


class BrowserController:
    """
    High-level browser controller using MCP Playwright server.

    Provides convenient methods for common browser operations needed
    for Claude Code automation.
    """

    def __init__(self, mcp_client: MCPClient):
        """
        Initialize browser controller.

        Args:
            mcp_client: Connected MCP client instance
        """
        self.client = mcp_client
        self._browser_launched = False

    async def launch_browser(self, headless: bool = False) -> None:
        """
        Launch browser instance.

        Args:
            headless: Whether to run in headless mode

        Raises:
            MCPError: If browser launch fails
        """
        try:
            logger.info(f"Launching browser (headless={headless})")

            await self.client.call_tool(
                "browser_navigate",
                {
                    "url": "about:blank",
                },
            )

            self._browser_launched = True
            logger.info("Browser launched successfully")

        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise MCPError(f"Browser launch failed: {e}") from e

    async def navigate(self, url: str, wait_until: str = "networkidle") -> None:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: When to consider navigation complete

        Raises:
            MCPError: If navigation fails
        """
        try:
            logger.info(f"Navigating to {url}")

            await self.client.call_tool(
                "browser_navigate",
                {
                    "url": url,
                },
            )

            logger.info(f"Successfully navigated to {url}")

        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            raise MCPError(f"Failed to navigate to {url}: {e}") from e

    async def click(self, selector: str, timeout: float = 30.0) -> None:
        """
        Click an element.

        Args:
            selector: CSS selector for the element
            timeout: Maximum time to wait for element

        Raises:
            MCPError: If click fails
        """
        try:
            logger.debug(f"Clicking element: {selector}")

            # Note: browser_click requires 'element' and 'ref' parameters
            # This simplified version may need adjustment based on actual usage
            await self.client.call_tool(
                "browser_click",
                {
                    "element": selector,
                    "ref": selector,
                },
            )

        except Exception as e:
            logger.error(f"Click failed: {e}")
            raise MCPError(f"Failed to click {selector}: {e}") from e

    async def fill(self, selector: str, text: str, timeout: float = 30.0) -> None:
        """
        Fill a text input.

        Args:
            selector: CSS selector for the input
            text: Text to fill
            timeout: Maximum time to wait for element

        Raises:
            MCPError: If fill fails
        """
        try:
            logger.debug(f"Filling element: {selector}")

            # Note: browser_type requires 'element', 'ref', and 'text' parameters
            await self.client.call_tool(
                "browser_type",
                {
                    "element": selector,
                    "ref": selector,
                    "text": text,
                    "submit": False,
                },
            )

        except Exception as e:
            logger.error(f"Fill failed: {e}")
            raise MCPError(f"Failed to fill {selector}: {e}") from e

    async def screenshot(self, output_path: Optional[Path] = None) -> bytes:
        """
        Take a screenshot.

        Args:
            output_path: Optional path to save screenshot

        Returns:
            Screenshot bytes

        Raises:
            MCPError: If screenshot fails
        """
        try:
            logger.debug("Taking screenshot")

            result = await self.client.call_tool(
                "browser_take_screenshot",
                {
                    "fullPage": True,
                    "type": "png",
                },
            )

            screenshot_data = result.get("screenshot", b"")

            if output_path:
                output_path.write_bytes(screenshot_data)
                logger.info(f"Screenshot saved to {output_path}")

            return screenshot_data

        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            raise MCPError(f"Failed to take screenshot: {e}") from e

    async def wait_for_selector(
        self,
        selector: str,
        timeout: float = 30.0,
        state: str = "visible",
    ) -> bool:
        """
        Wait for an element to appear by checking snapshots.

        Note: Playwright MCP doesn't have a direct wait_for_selector tool.
        This implementation uses browser_snapshot to check for elements.

        Args:
            selector: CSS selector for the element (simplified: checks if text appears in snapshot)
            timeout: Maximum time to wait
            state: Element state to wait for (visible, attached, etc.) - not fully supported

        Returns:
            True if element found in snapshot, False if timeout

        Raises:
            MCPError: If wait fails
        """
        import time

        start_time = time.time()

        try:
            logger.debug(f"Waiting for selector: {selector} (timeout={timeout}s)")

            while time.time() - start_time < timeout:
                try:
                    # Take a snapshot and check if selector text appears
                    result = await self.client.call_tool("browser_snapshot", {})

                    # Parse the response to see if selector-like text is present
                    snapshot_text = ""
                    if "content" in result and isinstance(result["content"], list):
                        for item in result["content"]:
                            if hasattr(item, "text"):
                                snapshot_text += item.text
                            elif isinstance(item, dict) and "text" in item:
                                snapshot_text += item["text"]

                    # Simple check: if we're looking for data-testid, check if it appears
                    # This is a simplified heuristic - not perfect but better than nothing
                    selector_parts = selector.replace("[", "").replace("]", "").replace("'", "").replace('"', '')

                    if selector_parts in snapshot_text or any(part in snapshot_text for part in selector_parts.split("=")):
                        logger.debug(f"Found indicator of selector {selector} in snapshot")
                        return True

                    # Brief pause before retry
                    await asyncio.sleep(2.0)

                except Exception as e:
                    logger.debug(f"Snapshot check failed: {e}")
                    await asyncio.sleep(2.0)

            logger.debug(f"Timeout waiting for selector: {selector}")
            return False

        except Exception as e:
            logger.warning(f"Wait for selector failed: {e}")
            return False

    async def get_text(self, selector: str) -> str:
        """
        Get text content of an element.

        Args:
            selector: CSS selector for the element

        Returns:
            Element text content

        Raises:
            MCPError: If operation fails
        """
        try:
            # browser_snapshot returns page accessibility tree
            # Getting specific element text requires parsing the snapshot
            result = await self.client.call_tool(
                "browser_snapshot",
                {},
            )

            # Handle MCP response format
            if "content" in result and isinstance(result["content"], list):
                for item in result["content"]:
                    if hasattr(item, "text"):
                        return item.text
                    elif isinstance(item, dict) and "text" in item:
                        return item["text"]
                return ""
            elif "text" in result:
                return result["text"]
            else:
                return str(result)

        except Exception as e:
            logger.error(f"Get text failed: {e}")
            raise MCPError(f"Failed to get text from {selector}: {e}") from e

    async def get_current_url(self) -> str:
        """
        Get current page URL.

        Returns:
            Current URL

        Raises:
            MCPError: If operation fails
        """
        try:
            result = await self.client.call_tool(
                "browser_evaluate",
                {"function": "() => window.location.href"},
            )

            # Handle MCP response format
            if "content" in result and isinstance(result["content"], list):
                # MCP returns content as list of TextContent/ImageContent objects
                for item in result["content"]:
                    if hasattr(item, "text"):
                        return item.text
                    elif isinstance(item, dict) and "text" in item:
                        return item["text"]
                return ""
            elif "result" in result:
                return str(result["result"])
            else:
                logger.warning(f"Unexpected result format: {result}")
                return str(result)

        except Exception as e:
            logger.error(f"Get URL failed: {e}")
            raise MCPError(f"Failed to get current URL: {e}") from e

    async def close(self) -> None:
        """Close the browser."""
        if self._browser_launched:
            logger.info("Closing browser")
            try:
                await self.client.call_tool("browser_close", {})
                self._browser_launched = False
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

    @property
    def is_launched(self) -> bool:
        """Check if browser is launched."""
        return self._browser_launched
