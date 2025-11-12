"""
Element Discovery (HITL) - Human-in-the-Loop element identification.
Implements Story 4.3: Element Discovery
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from datetime import datetime

from ..mcp.browser import BrowserController


logger = logging.getLogger(__name__)


@dataclass
class ElementSelector:
    """Discovered element selector."""

    element_id: str  # Unique ID for this element type
    selector: str  # CSS selector
    xpath: Optional[str] = None  # Alternative XPath selector
    description: str = ""  # Human-readable description
    discovered_at: str = ""  # Timestamp of discovery
    confidence: float = 1.0  # Confidence score (0-1)

    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now().isoformat()


class ElementDiscovery:
    """
    Manages Human-in-the-Loop element discovery.

    Allows users to teach Conductor where UI elements are by:
    1. Taking screenshots when input needed
    2. User identifies element location
    3. System records selector
    4. Selector reused in future runs
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize element discovery.

        Args:
            storage_path: Path to store discovered selectors
        """
        self.storage_path = storage_path or (
            Path.home() / ".conductor" / "element_selectors.json"
        )
        self.selectors: Dict[str, ElementSelector] = {}
        self._load_selectors()

    def _load_selectors(self) -> None:
        """Load previously discovered selectors from storage."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.selectors = {
                        k: ElementSelector(**v) for k, v in data.items()
                    }
                logger.info(f"Loaded {len(self.selectors)} element selectors")
            except Exception as e:
                logger.error(f"Failed to load selectors: {e}")

    def _save_selectors(self) -> None:
        """Save selectors to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                data = {k: asdict(v) for k, v in self.selectors.items()}
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.selectors)} element selectors")
        except Exception as e:
            logger.error(f"Failed to save selectors: {e}")

    def get_selector(self, element_id: str) -> Optional[ElementSelector]:
        """
        Get a discovered selector.

        Args:
            element_id: ID of the element

        Returns:
            ElementSelector if found, None otherwise
        """
        return self.selectors.get(element_id)

    def has_selector(self, element_id: str) -> bool:
        """Check if selector exists."""
        return element_id in self.selectors

    def record_selector(
        self,
        element_id: str,
        selector: str,
        description: str = "",
        xpath: Optional[str] = None,
        confidence: float = 1.0,
    ) -> ElementSelector:
        """
        Record a discovered element selector.

        Args:
            element_id: Unique ID for this element type
            selector: CSS selector
            description: Human-readable description
            xpath: Optional XPath selector
            confidence: Confidence score (0-1)

        Returns:
            Created ElementSelector
        """
        element = ElementSelector(
            element_id=element_id,
            selector=selector,
            xpath=xpath,
            description=description,
            confidence=confidence,
        )

        self.selectors[element_id] = element
        self._save_selectors()

        logger.info(f"Recorded selector for {element_id}: {selector}")
        return element

    def get_all_selectors(self) -> List[ElementSelector]:
        """Get all discovered selectors."""
        return list(self.selectors.values())

    async def discover_element(
        self,
        browser: BrowserController,
        element_id: str,
        description: str,
        prompt_user_callback,
    ) -> Optional[ElementSelector]:
        """
        Discover an element through human interaction.

        Args:
            browser: Browser controller
            element_id: ID for this element
            description: Description to show user
            prompt_user_callback: Async function to prompt user for selector

        Returns:
            ElementSelector if discovered, None otherwise
        """
        # Take screenshot
        screenshot = await browser.screenshot()

        # Prompt user to identify element
        # This would show the screenshot and let user click/provide selector
        selector = await prompt_user_callback(screenshot, description)

        if selector:
            return self.record_selector(
                element_id=element_id, selector=selector, description=description
            )

        return None

    def suggest_selectors(self, element_type: str) -> List[str]:
        """
        Suggest common selectors for an element type.

        Args:
            element_type: Type of element (submit_button, input_field, etc.)

        Returns:
            List of suggested selectors to try
        """
        suggestions = {
            "submit_button": [
                "button[type='submit']",
                "button:has-text('Submit')",
                "input[type='submit']",
                "[data-testid='submit-button']",
            ],
            "input_field": [
                "textarea[placeholder*='message']",
                "input[type='text']",
                "textarea.prompt-input",
                "[contenteditable='true']",
            ],
            "pr_button": [
                "button:has-text('Create Pull Request')",
                "button:has-text('Create PR')",
                "[data-testid='create-pr-button']",
                "a:has-text('Pull Request')",
            ],
            "repository_selector": [
                "[data-testid='repository-select']",
                "select[name='repository']",
                "button:has-text('Select Repository')",
            ],
        }

        return suggestions.get(element_type, [])
