"""
MCP (Model Context Protocol) integration for browser control.
"""

from .client import MCPClient, MCPError, MCPConnectionError
from .browser import BrowserController

__all__ = ["MCPClient", "MCPError", "MCPConnectionError", "BrowserController"]
