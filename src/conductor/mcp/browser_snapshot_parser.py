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
    snapshot_text = extract_snapshot_text(snapshot)
    if not snapshot_text:
        return None

    elements = parse_elements(snapshot_text)
    if not elements:
        return None

    return search_elements(elements, description_lower)


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


def extract_snapshot_text(snapshot: Union[str, Dict]) -> str:
    """Extract raw snapshot text from various formats."""
    if isinstance(snapshot, str):
        return snapshot

    if isinstance(snapshot, dict):
        content = snapshot.get("content")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            for item in content:
                text = None
                if hasattr(item, "text"):
                    text = item.text
                elif isinstance(item, dict):
                    text = item.get("text")

                if text:
                    return text

    return ""


def parse_elements(text: str) -> List[Dict[str, str]]:
    """
    Parse snapshot text into a flat list of simplified elements.

    Each element contains:
    - type: button, textbox, menuitem, etc.
    - name/text: Human-readable label if present
    - ref: Element reference ID (e.g., e123)
    - raw: Raw line for fallback matching
    """
    elements: List[Dict[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(("-", "•")):
            continue

        ref_match = re.search(r"\[ref=([^\]]+)\]", line)
        if not ref_match:
            continue

        element_ref = ref_match.group(1)

        # Remove list marker and trailing colon
        body = line.lstrip("-•").strip()
        if body.endswith(":"):
            body = body[:-1]

        # Handle lines wrapped in quotes
        if body.startswith("'") and body.endswith("'"):
            body = body[1:-1]

        # Extract element type
        type_match = re.match(r"([a-zA-Z]+)", body)
        if not type_match:
            continue

        element_type = type_match.group(1).lower()
        remainder = body[len(type_match.group(0)):].strip()

        # Extract quoted name if present
        element_name = ""
        if remainder.startswith('"'):
            parts = remainder.split('"')
            if len(parts) >= 2:
                element_name = parts[1]
        elif remainder.startswith("'"):
            parts = remainder.split("'")
            if len(parts) >= 2:
                element_name = parts[1]

        elements.append(
            {
                "type": element_type,
                "name": element_name,
                "text": element_name or remainder,
                "ref": element_ref,
                "raw": line.lower(),
            }
        )

    return elements


def search_elements(elements: List[Dict[str, str]], description_lower: str) -> Optional[str]:
    """
    Search the parsed element list for a matching description.

    Args:
        elements: List of element dictionaries
        description_lower: Lowercase description to match

    Returns:
        Element ref if found, None otherwise
    """
    for element in elements:
        element_type = element.get("type", "")
        element_name = element.get("name", "")
        element_text = element.get("text", "")
        element_ref = element.get("ref")
        element_raw = element.get("raw", "")

        # Check various matching patterns
        if "submit" in description_lower and "button" in description_lower:
            if element_type == "button" and "submit" in element_raw:
                if "[disabled]" not in element_raw:
                    return element_ref

        elif "select repository" in description_lower:
            if element_type == "button" and "select repository" in element_raw:
                return element_ref

        elif "repository" in description_lower and "option" in description_lower:
            # Extract repository info from description
            # Format: "Conductor karolswdev repository option"
            parts = description_lower.replace("repository option", "").strip().split()
            if len(parts) >= 1:
                repo_name = parts[0]
                owner = parts[1] if len(parts) > 1 else ""

            if element_type in ("menuitem", "button", "generic", "link", "paragraph"):
                element_text_lower = element_text.lower()
                # Check if repo name and owner match
                if repo_name in element_text_lower:
                    if not owner or owner in element_text_lower:
                        return element_ref

        elif "message" in description_lower and ("input" in description_lower or "textbox" in description_lower):
            if element_type == "textbox":
                # Match on placeholder or name containing "todo" or "message"
                placeholder = element_text.lower()
                if "todo" in element_name.lower() or "todo" in placeholder or "message" in placeholder:
                    return element_ref

        elif "not now" in description_lower:
            if element_type == "button" and "not now" in element_raw:
                return element_ref

        elif "create pr" in description_lower:
            if element_type == "button" and "create pr" in element_raw:
                return element_ref

        elif "repository" in description_lower and "button" in description_lower:
            if element_type == "button":
                if "/" in element_text or "repository" in element_raw:
                    return element_ref

        # Generic button search
        elif "button" in description_lower:
            if element_type == "button":
                # Extract button text from description
                button_text = description_lower.replace(" button", "").replace("button", "").strip()
                if button_text and (
                    button_text in element_text.lower()
                    or button_text in element_name.lower()
                    or button_text in element_raw
                ):
                    return element_ref

    return None


def is_create_pr_button_enabled(snapshot_text: str) -> bool:
    """
    Check if Create PR button is enabled in snapshot.

    Args:
        snapshot_text: Raw snapshot text or YAML

    Returns:
        True if Create PR button exists and is enabled, False otherwise
    """
    text = extract_snapshot_text(snapshot_text)
    if not text:
        return False

    elements = parse_elements(text)
    for element in elements:
        if element.get("type") == "button" and "create pr" in element.get("raw", ""):
            # Assume disabled if the raw line mentions [disabled]
            return "[disabled]" not in element.get("raw", "")

    return False

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
