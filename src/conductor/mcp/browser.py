"""
Browser controller using MCP Playwright integration.

Updated to properly use accessibility snapshots instead of CSS selectors.
"""

import asyncio
import logging
import re
import yaml
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from .client import MCPClient, MCPError
from .browser_snapshot_parser import (
    find_element_in_snapshot,
    is_create_pr_button_enabled as check_create_pr_button_enabled,
    extract_branch_name as extract_branch_name_from_text,
)


logger = logging.getLogger(__name__)


class BrowserController:
    """
    High-level browser controller using MCP Playwright server.

    Provides convenient methods for common browser operations needed
    for Claude Code automation using accessibility snapshots.
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

    async def get_snapshot(self) -> Dict[str, Any]:
        """
        Get accessibility snapshot of the current page.

        Returns:
            Snapshot data

        Raises:
            MCPError: If snapshot fails
        """
        try:
            result = await self.client.call_tool("browser_snapshot", {})
            return result
        except Exception as e:
            logger.error(f"Failed to get snapshot: {e}")
            raise MCPError(f"Failed to get snapshot: {e}") from e

    def _find_element_in_snapshot(self, snapshot: Any, description: str) -> Optional[str]:
        """
        Parse accessibility snapshot to find element ref.

        Args:
            snapshot: The accessibility snapshot
            description: Human-readable description of the element

        Returns:
            Element ref (e.g., "e226") or None if not found
        """
        # Delegate to the imported parser function
        return find_element_in_snapshot(snapshot, description)

    async def click(self, element_description: str, timeout: float = 30.0) -> None:
        """
        Click an element using accessibility snapshot.

        Args:
            element_description: Human-readable description of the element
            timeout: Maximum time to wait for element

        Raises:
            MCPError: If click fails
        """
        try:
            logger.debug(f"Clicking element: {element_description}")

            # Get snapshot first
            snapshot = await self.get_snapshot()

            # Find element ref in snapshot
            element_ref = self._find_element_in_snapshot(snapshot, element_description)

            if not element_ref:
                logger.warning(f"Element not found in snapshot: {element_description}")
                # Try alternative approach - might be a dynamic element
                raise MCPError(f"Element not found: {element_description}")

            logger.debug(f"Found element ref: {element_ref} for {element_description}")

            # Click with proper parameters
            await self.client.call_tool(
                "browser_click",
                {
                    "element": element_description,  # Human-readable
                    "ref": element_ref,              # Actual ref from snapshot
                },
            )

            logger.info(f"Successfully clicked: {element_description}")

        except Exception as e:
            logger.error(f"Click failed for '{element_description}': {e}")
            raise MCPError(f"Failed to click {element_description}: {e}") from e

    async def fill(self, element_description: str, text: str, timeout: float = 30.0) -> None:
        """
        Fill a text input using accessibility snapshot.

        Args:
            element_description: Human-readable description of the element
            text: Text to fill
            timeout: Maximum time to wait for element

        Raises:
            MCPError: If fill fails
        """
        try:
            logger.debug(f"Filling element: {element_description}")

            # Get snapshot first
            snapshot = await self.get_snapshot()

            # Find element ref in snapshot
            element_ref = self._find_element_in_snapshot(snapshot, element_description)

            if not element_ref:
                logger.warning(f"Element not found in snapshot: {element_description}")
                raise MCPError(f"Element not found: {element_description}")

            logger.debug(f"Found element ref: {element_ref} for {element_description}")

            # Type with proper parameters
            await self.client.call_tool(
                "browser_type",
                {
                    "element": element_description,  # Human-readable
                    "ref": element_ref,              # Actual ref from snapshot
                    "text": text,
                    "submit": False,                 # Don't auto-submit
                },
            )

            logger.info(f"Successfully filled: {element_description}")

        except Exception as e:
            logger.error(f"Fill failed for '{element_description}': {e}")
            raise MCPError(f"Failed to fill {element_description}: {e}") from e

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

    async def wait_for_element(
        self,
        element_description: str,
        timeout: float = 30.0,
        check_interval: float = 2.0
    ) -> bool:
        """
        Wait for an element to appear in accessibility snapshot.

        Args:
            element_description: Human-readable description of the element
            timeout: Maximum time to wait
            check_interval: How often to check

        Returns:
            True if element found, False if timeout

        Raises:
            MCPError: If wait fails
        """
        import time

        start_time = time.time()

        try:
            logger.debug(f"Waiting for element: {element_description} (timeout={timeout}s)")

            while time.time() - start_time < timeout:
                try:
                    # Take a snapshot and check for element
                    snapshot = await self.get_snapshot()
                    element_ref = self._find_element_in_snapshot(snapshot, element_description)

                    if element_ref:
                        logger.debug(f"Found element: {element_description} with ref: {element_ref}")
                        return True

                    # Brief pause before retry
                    await asyncio.sleep(check_interval)

                except Exception as e:
                    logger.debug(f"Snapshot check failed: {e}")
                    await asyncio.sleep(check_interval)

            logger.debug(f"Timeout waiting for element: {element_description}")
            return False

        except Exception as e:
            logger.warning(f"Wait for element failed: {e}")
            return False

    async def get_text(self, element_description: str = "body") -> str:
        """
        Get text content from the page or a specific element.

        Args:
            element_description: Description of element (default: entire page)

        Returns:
            Element text content

        Raises:
            MCPError: If operation fails
        """
        try:
            # Get accessibility snapshot
            snapshot = await self.get_snapshot()

            # Extract text from snapshot
            snapshot_text = ""
            if "content" in snapshot and isinstance(snapshot["content"], list):
                for item in snapshot["content"]:
                    if hasattr(item, "text"):
                        snapshot_text = item.text
                    elif isinstance(item, dict) and "text" in item:
                        snapshot_text = item["text"]

            return snapshot_text

        except Exception as e:
            logger.error(f"Get text failed: {e}")
            raise MCPError(f"Failed to get text: {e}") from e

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

    async def create_tab(self, url: Optional[str] = None) -> int:
        """
        Create a new browser tab, optionally navigating to a URL.

        Args:
            url: Optional URL to navigate to in the new tab

        Returns:
            Index of the new tab

        Raises:
            MCPError: If tab creation fails
        """
        try:
            logger.debug(f"Creating new tab{f' with URL {url}' if url else ''}")

            params = {"action": "new"}
            if url:
                params["url"] = url

            result = await self.client.call_tool(
                "browser_tabs",
                params,
            )

            # Get the list of tabs to find the new one
            tabs = await self.list_tabs()
            new_tab_index = len(tabs) - 1

            logger.info(f"Created new tab at index {new_tab_index}{f' navigated to {url}' if url else ''}")
            return new_tab_index

        except Exception as e:
            logger.error(f"Failed to create tab: {e}")
            raise MCPError(f"Tab creation failed: {e}") from e

    async def list_tabs(self) -> list:
        """
        List all open browser tabs.

        Returns:
            List of tab information

        Raises:
            MCPError: If listing tabs fails
        """
        try:
            result = await self.client.call_tool(
                "browser_tabs",
                {
                    "action": "list",
                },
            )

            # Parse the result to get tab list
            if "content" in result and isinstance(result["content"], list):
                for item in result["content"]:
                    if hasattr(item, "text"):
                        return self._parse_tab_list(item.text)
                    elif isinstance(item, dict) and "text" in item:
                        return self._parse_tab_list(item["text"])
                return []
            elif "tabs" in result:
                return result["tabs"]
            else:
                return []

        except Exception as e:
            logger.error(f"Failed to list tabs: {e}")
            raise MCPError(f"Tab listing failed: {e}") from e

    async def switch_tab(self, index: int) -> None:
        """
        Switch to a specific browser tab.

        Args:
            index: Index of the tab to switch to

        Raises:
            MCPError: If tab switch fails
        """
        try:
            logger.debug(f"Switching to tab {index}")

            await self.client.call_tool(
                "browser_tabs",
                {
                    "action": "select",
                    "index": index,
                },
            )

            logger.info(f"Switched to tab {index}")

        except Exception as e:
            logger.error(f"Failed to switch to tab {index}: {e}")
            raise MCPError(f"Tab switch failed: {e}") from e

    async def close_tab(self, index: int) -> None:
        """
        Close a specific browser tab.

        Args:
            index: Index of the tab to close

        Raises:
            MCPError: If tab close fails
        """
        try:
            logger.debug(f"Closing tab {index}")

            await self.client.call_tool(
                "browser_tabs",
                {
                    "action": "close",
                    "index": index,
                },
            )

            logger.info(f"Closed tab {index}")

        except Exception as e:
            logger.error(f"Failed to close tab {index}: {e}")
            raise MCPError(f"Tab close failed: {e}") from e

    def _parse_tab_list(self, text: str) -> list:
        """
        Parse tab list from text content.

        Args:
            text: Text content containing tab information

        Returns:
            List of tab info dictionaries
        """
        # Simple parsing - this may need adjustment based on actual format
        tabs = []
        lines = text.strip().split("\n")

        for i, line in enumerate(lines):
            if line.strip():
                tabs.append({"index": i, "title": line.strip()})

        return tabs

    def extract_branch_name(self, snapshot_text: str) -> Optional[str]:
        """
        Extract Claude branch name from snapshot text.

        Args:
            snapshot_text: Text from accessibility snapshot

        Returns:
            Branch name if found (e.g., "claude/test-automation-abc123")
        """
        # Delegate to the imported parser function
        return extract_branch_name_from_text(snapshot_text)

    def is_create_pr_button_enabled(self, snapshot_text: str) -> bool:
        """
        Check if Create PR button is enabled in snapshot.

        Args:
            snapshot_text: Text from accessibility snapshot

        Returns:
            True if Create PR button exists and is not disabled
        """
        # Delegate to the imported parser function
        return check_create_pr_button_enabled(snapshot_text)

    async def dismiss_notification_dialog(self) -> bool:
        """
        Dismiss notification dialog if present.

        Returns:
            True if dialog was dismissed, False if no dialog found
        """
        try:
            # Check for notification dialog
            snapshot = await self.get_snapshot()

            # Look for "Not Now" button
            element_ref = self._find_element_in_snapshot(snapshot, "Not Now button")

            if element_ref:
                logger.info("Found notification dialog, dismissing...")
                await self.click("Not Now button")
                await asyncio.sleep(1.0)
                return True

            return False

        except Exception as e:
            logger.debug(f"No notification dialog found or failed to dismiss: {e}")
            return False

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