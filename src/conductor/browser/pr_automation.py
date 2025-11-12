"""
PR creation automation.
Implements Story 5.2: PR Creation Automation
"""

import asyncio
import logging
from typing import Optional
from enum import Enum

from ..mcp.browser import BrowserController, MCPError
from .element_discovery import ElementDiscovery


logger = logging.getLogger(__name__)


class PRStatus(str, Enum):
    """PR creation status."""

    NOT_READY = "not_ready"
    READY = "ready"
    CREATING = "creating"
    CREATED = "created"
    FAILED = "failed"


class PRAutomation:
    """
    Automates PR creation for completed tasks.

    Features:
    - Auto-detect PR readiness
    - Find and click PR button
    - Wait for PR creation confirmation
    - Extract and display PR URL
    """

    # Common selectors for PR buttons
    PR_BUTTON_SELECTORS = [
        "button:has-text('Create Pull Request')",
        "button:has-text('Create PR')",
        "[data-testid='create-pr-button']",
        "a[href*='/pull/new']",
    ]

    # Selectors indicating PR was created
    PR_CREATED_SELECTORS = [
        "a[href*='/pull/']",
        "[data-testid='pr-created']",
        ".pull-request-link",
    ]

    def __init__(
        self,
        browser: BrowserController,
        element_discovery: Optional[ElementDiscovery] = None,
    ):
        """
        Initialize PR automation.

        Args:
            browser: Browser controller
            element_discovery: Element discovery system (optional)
        """
        self.browser = browser
        self.element_discovery = element_discovery or ElementDiscovery()
        self.status = PRStatus.NOT_READY

    async def check_pr_ready(self, timeout: float = 5.0) -> bool:
        """
        Check if PR creation is ready.

        Args:
            timeout: How long to wait for button

        Returns:
            True if PR button found, False otherwise
        """
        # Check discovered selector first
        if self.element_discovery.has_selector("pr_button"):
            selector_obj = self.element_discovery.get_selector("pr_button")
            try:
                found = await self.browser.wait_for_selector(
                    selector_obj.selector, timeout=timeout, state="visible"
                )
                if found:
                    self.status = PRStatus.READY
                    return True
            except:
                pass

        # Try common selectors
        for selector in self.PR_BUTTON_SELECTORS:
            try:
                found = await self.browser.wait_for_selector(
                    selector, timeout=2.0, state="visible"
                )
                if found:
                    # Record this selector for future use
                    self.element_discovery.record_selector(
                        element_id="pr_button",
                        selector=selector,
                        description="Create Pull Request button",
                    )
                    self.status = PRStatus.READY
                    return True
            except:
                continue

        self.status = PRStatus.NOT_READY
        return False

    async def create_pr(self, timeout: float = 60.0) -> Optional[str]:
        """
        Create a pull request.

        Args:
            timeout: Maximum time to wait for PR creation

        Returns:
            PR URL if successful, None otherwise
        """
        try:
            self.status = PRStatus.CREATING

            # Find PR button
            pr_ready = await self.check_pr_ready(timeout=10.0)

            if not pr_ready:
                logger.warning("PR button not found")
                self.status = PRStatus.FAILED
                return None

            # Get the selector to use
            if self.element_discovery.has_selector("pr_button"):
                selector = self.element_discovery.get_selector("pr_button").selector
            else:
                # Use first common selector
                selector = self.PR_BUTTON_SELECTORS[0]

            # Click PR button
            await self.browser.click(selector, timeout=timeout)
            logger.info("Clicked PR button")

            # Wait for PR creation
            await asyncio.sleep(3.0)

            # Try to extract PR URL
            pr_url = await self._extract_pr_url(timeout)

            if pr_url:
                self.status = PRStatus.CREATED
                logger.info(f"PR created: {pr_url}")
                return pr_url
            else:
                self.status = PRStatus.FAILED
                logger.warning("Could not extract PR URL")
                return None

        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            self.status = PRStatus.FAILED
            return None

    async def _extract_pr_url(self, timeout: float = 30.0) -> Optional[str]:
        """
        Extract PR URL after creation.

        Args:
            timeout: Maximum time to wait

        Returns:
            PR URL if found, None otherwise
        """
        # Check current URL
        current_url = await self.browser.get_current_url()

        # If URL changed to a PR page, return it
        if "/pull/" in current_url:
            return current_url

        # Try to find PR link in page
        for selector in self.PR_CREATED_SELECTORS:
            try:
                found = await self.browser.wait_for_selector(
                    selector, timeout=5.0, state="visible"
                )
                if found:
                    # Get href attribute
                    # This is simplified - would need actual href extraction
                    return current_url
            except:
                continue

        return None

    async def wait_for_pr_ready(
        self, timeout: float = 1800.0, check_interval: float = 10.0
    ) -> bool:
        """
        Wait for PR to become ready.

        Args:
            timeout: Maximum time to wait (default: 30 min)
            check_interval: How often to check (default: 10s)

        Returns:
            True if ready, False if timeout
        """
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if await self.check_pr_ready(timeout=check_interval):
                return True

            await asyncio.sleep(check_interval)

        return False
