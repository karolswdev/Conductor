"""
Authentication flow for Claude Code.
"""

import asyncio
import logging
from enum import Enum
from typing import Optional
from datetime import datetime, timedelta

from ..mcp.browser import BrowserController
from ..mcp.client import MCPError


logger = logging.getLogger(__name__)


class AuthStatus(str, Enum):
    """Authentication status."""

    NOT_STARTED = "not_started"
    BROWSER_LAUNCHED = "browser_launched"
    WAITING_FOR_USER = "waiting_for_user"
    CHECKING_LOGIN = "checking_login"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AuthenticationFlow:
    """
    Manages the manual authentication flow for Claude Code.

    This implements Story 2.1: Manual Authentication Flow
    - Launches browser automatically
    - Shows countdown timer
    - Waits for user confirmation
    - Detects successful login
    """

    CLAUDE_CODE_URL = "https://claude.ai/code"

    # Selectors for detecting successful login
    LOGIN_SUCCESS_SELECTORS = [
        "[data-testid='session-list']",  # Session list visible
        "[data-testid='new-session-button']",  # New session button
        ".session-container",  # Session container
    ]

    def __init__(
        self,
        browser: BrowserController,
        timeout: int = 120,
        check_interval: float = 2.0,
    ):
        """
        Initialize authentication flow.

        Args:
            browser: Browser controller instance
            timeout: Authentication timeout in seconds (default: 120s = 2 min)
            check_interval: How often to check for login success in seconds
        """
        self.browser = browser
        self.timeout = timeout
        self.check_interval = check_interval
        self.status = AuthStatus.NOT_STARTED
        self._start_time: Optional[datetime] = None

    async def start(self, headless: bool = False, wait_for_user_input: bool = True) -> AuthStatus:
        """
        Start the authentication flow.

        Args:
            headless: Whether to run browser in headless mode (default: False for manual auth)
            wait_for_user_input: If True, wait for user to press Enter. If False, use auto-detection.

        Returns:
            Final authentication status

        Raises:
            MCPError: If browser operations fail
        """
        self.status = AuthStatus.NOT_STARTED
        self._start_time = datetime.now()

        try:
            # Step 1: Launch browser
            logger.info("Starting authentication flow")
            self.status = AuthStatus.BROWSER_LAUNCHED

            if not self.browser.is_launched:
                await self.browser.launch_browser(headless=headless)

            # Step 2: Navigate to Claude Code
            logger.info(f"Navigating to {self.CLAUDE_CODE_URL}")
            await self.browser.navigate(self.CLAUDE_CODE_URL)

            # Step 3: Wait for user to authenticate
            self.status = AuthStatus.WAITING_FOR_USER
            logger.info("Waiting for user authentication")

            if wait_for_user_input:
                # Simple approach: wait for user confirmation
                success = await self._wait_for_user_confirmation()
            else:
                # Complex approach: try to auto-detect login (less reliable)
                success = await self._wait_for_login()

            if success:
                self.status = AuthStatus.AUTHENTICATED
                logger.info("Authentication successful!")
                return AuthStatus.AUTHENTICATED
            else:
                self.status = AuthStatus.TIMEOUT
                logger.warning("Authentication timed out")
                return AuthStatus.TIMEOUT

        except MCPError as e:
            logger.error(f"Authentication failed: {e}")
            self.status = AuthStatus.FAILED
            raise

        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            self.status = AuthStatus.FAILED
            raise MCPError(f"Authentication failed: {e}") from e

    async def _wait_for_user_confirmation(self) -> bool:
        """
        Wait for user to confirm they've logged in by pressing Enter.

        Returns:
            True if user confirmed, False if timeout
        """
        import sys

        # Use asyncio to run input() in thread pool to avoid blocking
        loop = asyncio.get_event_loop()

        try:
            # Wait with timeout
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: input("\nPress Enter after you have logged in to Claude Code in the browser... ")
                ),
                timeout=self.timeout
            )

            logger.info("User confirmed authentication")
            return True

        except asyncio.TimeoutError:
            logger.warning(f"User did not confirm authentication within {self.timeout}s")
            return False

    async def _wait_for_login(self) -> bool:
        """
        Wait for successful login by polling for specific elements.

        Returns:
            True if login detected, False if timeout
        """
        end_time = datetime.now() + timedelta(seconds=self.timeout)
        last_progress_log = 0

        while datetime.now() < end_time:
            self.status = AuthStatus.CHECKING_LOGIN
            elapsed = (datetime.now() - self._start_time).total_seconds()
            remaining = self.timeout - elapsed

            # Check if any of the success selectors are present
            for selector in self.LOGIN_SUCCESS_SELECTORS:
                try:
                    found = await self.browser.wait_for_selector(
                        selector,
                        timeout=self.check_interval,
                        state="visible",
                    )

                    if found:
                        logger.info(f"Login success detected via selector: {selector}")
                        return True

                except Exception as e:
                    logger.debug(f"Selector {selector} not found: {e}")
                    continue

            # Log progress every 10 seconds to avoid spam
            if elapsed - last_progress_log >= 10:
                logger.info(f"Still waiting for login... ({remaining:.0f}s remaining)")
                last_progress_log = elapsed

            # Brief pause before next check
            await asyncio.sleep(self.check_interval)

        logger.warning("Authentication timeout - login was not detected")
        logger.warning("Note: Detection may have failed even if you logged in successfully")
        logger.warning("If you completed login, the app may still work")
        return False

    async def check_authenticated(self) -> bool:
        """
        Check if currently authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        try:
            # Check if we can see the session list
            for selector in self.LOGIN_SUCCESS_SELECTORS:
                found = await self.browser.wait_for_selector(
                    selector,
                    timeout=5.0,
                    state="visible",
                )
                if found:
                    return True

            return False

        except Exception as e:
            logger.debug(f"Authentication check failed: {e}")
            return False

    def get_elapsed_time(self) -> float:
        """
        Get elapsed time since authentication started.

        Returns:
            Elapsed time in seconds, or 0 if not started
        """
        if self._start_time is None:
            return 0.0

        return (datetime.now() - self._start_time).total_seconds()

    def get_remaining_time(self) -> float:
        """
        Get remaining time before timeout.

        Returns:
            Remaining time in seconds, or 0 if expired
        """
        elapsed = self.get_elapsed_time()
        remaining = self.timeout - elapsed
        return max(0.0, remaining)

    @property
    def is_authenticated(self) -> bool:
        """Check if authentication is successful."""
        return self.status == AuthStatus.AUTHENTICATED

    @property
    def is_active(self) -> bool:
        """Check if authentication flow is active."""
        return self.status in [
            AuthStatus.BROWSER_LAUNCHED,
            AuthStatus.WAITING_FOR_USER,
            AuthStatus.CHECKING_LOGIN,
        ]
