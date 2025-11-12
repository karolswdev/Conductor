"""
Snapshot parsing utilities for BrowserController.
Separating this out to make testing easier.
"""

import re
import yaml
import logging
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)


def find_element_in_snapshot(snapshot: Union[str, Dict], description: str) -> Optional[str]:
    """
    Parse accessibility snapshot to find element ref.

    Args:
        snapshot: The accessibility snapshot (raw string, parsed dict, or response dict)
        description: Human-readable description of the element

    Returns:
        Element ref (e.g., "e226") or None if not found
    """
    description_lower = description.lower()

    # Parse the snapshot into a usable structure
    parsed = parse_snapshot(snapshot)
    if not parsed:
        return None

    # Navigate to page content
    content = get_content_from_parsed(parsed)
    if not content:
        return None

    # Search through elements
    return search_elements(content, description_lower)


def parse_snapshot(snapshot: Union[str, Dict]) -> Optional[Dict]:
    """Parse various snapshot formats into a dictionary."""
    if isinstance(snapshot, str):
        try:
            return yaml.safe_load(snapshot)
        except Exception as e:
            logger.warning(f"Failed to parse snapshot as YAML: {e}")
            return None

    elif isinstance(snapshot, dict):
        # Check if it has a 'content' key with string value (raw response)
        if "content" in snapshot and isinstance(snapshot["content"], str):
            try:
                return yaml.safe_load(snapshot["content"])
            except Exception as e:
                logger.warning(f"Failed to parse snapshot content as YAML: {e}")
                return None
        else:
            return snapshot

    return None


def get_content_from_parsed(parsed: Dict) -> Optional[List]:
    """Extract content list from parsed snapshot."""
    if "page" in parsed:
        return parsed["page"].get("content", [])
    elif "content" in parsed:
        return parsed["content"]
    return None


def search_elements(elements: List, description_lower: str) -> Optional[str]:
    """
    Recursively search through elements for matching description.

    Args:
        elements: List of element dictionaries
        description_lower: Lowercase description to match

    Returns:
        Element ref if found, None otherwise
    """
    for element in elements:
        if not isinstance(element, dict):
            continue

        element_type = element.get("type", "")
        element_name = element.get("name", "")
        element_text = element.get("text", "")
        element_ref = element.get("ref")

        # Check various matching patterns
        if "submit" in description_lower and "button" in description_lower:
            if element_type == "button" and "submit" in element_name.lower():
                # Skip if disabled
                if not element.get("disabled", False):
                    return element_ref

        elif "select repository" in description_lower:
            if element_type == "button" and "select repository" in element_text.lower():
                return element_ref

        elif "repository" in description_lower and "option" in description_lower:
            # Extract repository info from description
            # Format: "Conductor karolswdev repository option"
            parts = description_lower.replace("repository option", "").strip().split()
            if len(parts) >= 1:
                repo_name = parts[0]
                owner = parts[1] if len(parts) > 1 else ""

                if element_type == "menuitem":
                    element_text_lower = element_text.lower()
                    # Check if repo name and owner match
                    if repo_name in element_text_lower:
                        if not owner or owner in element_text_lower:
                            return element_ref

        elif "message" in description_lower and ("input" in description_lower or "textbox" in description_lower):
            if element_type == "textbox":
                # Match on placeholder or name containing "todo" or "message"
                placeholder = element.get("placeholder", "").lower()
                if "todo" in element_name.lower() or "todo" in placeholder:
                    return element_ref

        elif "not now" in description_lower:
            if element_type == "button" and "not now" in element_text.lower():
                return element_ref

        elif "create pr" in description_lower:
            if element_type == "button" and "create pr" in element_text.lower():
                return element_ref

        # Generic button search
        elif "button" in description_lower:
            if element_type == "button":
                # Extract button text from description
                button_text = description_lower.replace(" button", "").replace("button", "").strip()
                if button_text in element_text.lower() or button_text in element_name.lower():
                    return element_ref

        # Check nested items (e.g., menu items)
        if "items" in element:
            result = search_elements(element["items"], description_lower)
            if result:
                return result

    return None


def is_create_pr_button_enabled(snapshot_text: str) -> bool:
    """
    Check if Create PR button is enabled in snapshot.

    Args:
        snapshot_text: Raw snapshot text or YAML

    Returns:
        True if Create PR button exists and is enabled, False otherwise
    """
    parsed = parse_snapshot(snapshot_text)
    if not parsed:
        return False

    content = get_content_from_parsed(parsed)
    if not content:
        return False

    for element in content:
        if isinstance(element, dict):
            if element.get("type") == "button":
                if "create pr" in element.get("text", "").lower():
                    # Button exists - check if disabled
                    return not element.get("disabled", False)

    return False


def extract_branch_name(snapshot_text: str) -> Optional[str]:
    """
    Extract git branch name from snapshot.

    Args:
        snapshot_text: Raw snapshot text

    Returns:
        Branch name if found, None otherwise
    """
    # Look for patterns like "claude/test-conductor-011CV4beKrFjCAcPw3r7tC3u"
    patterns = [
        r'claude/[a-zA-Z0-9\-_]+',
        r'Branch:\s*(claude/[a-zA-Z0-9\-_]+)',
        r'Working on:\s*(claude/[a-zA-Z0-9\-_]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, snapshot_text)
        if match:
            if "Branch:" in pattern or "Working on:" in pattern:
                return match.group(1)
            return match.group(0)

    return None