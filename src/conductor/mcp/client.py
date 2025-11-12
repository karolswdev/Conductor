"""
MCP client for connecting to and communicating with MCP servers.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Base exception for MCP-related errors."""

    pass


class MCPConnectionError(MCPError):
    """Exception raised when MCP connection fails."""

    pass


class MCPClient:
    """
    Client for communicating with MCP servers.

    Supports both stdio and HTTP/SSE transports based on server URL.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize MCP client.

        Args:
            server_url: URL of the MCP server (http://... for SSE, stdio://... for stdio)
            timeout: Connection timeout in seconds
            max_retries: Maximum number of connection retries
        """
        self.server_url = server_url or "stdio://playwright-mcp"
        self.timeout = timeout
        self.max_retries = max_retries
        self._connected = False
        self._session: Optional[ClientSession] = None
        self._read = None
        self._write = None
        self._session_context = None

    async def connect(self) -> None:
        """
        Connect to the MCP server with exponential backoff retry.

        Raises:
            MCPConnectionError: If connection fails after all retries
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Connecting to MCP server at {self.server_url} "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )

                # Determine transport type based on URL
                parsed_url = urlparse(self.server_url)

                if parsed_url.scheme in ("http", "https"):
                    # HTTP/SSE transport
                    await self._connect_sse()
                elif parsed_url.scheme == "stdio":
                    # Stdio transport
                    await self._connect_stdio()
                else:
                    raise MCPConnectionError(f"Unsupported protocol: {parsed_url.scheme}")

                self._connected = True
                logger.info("Successfully connected to MCP server")
                return

            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")

                if attempt < self.max_retries - 1:
                    delay = min(2**attempt, 10)  # Exponential backoff, max 10s
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    raise MCPConnectionError(
                        f"Failed to connect after {self.max_retries} attempts: {e}"
                    ) from e

    async def _connect_sse(self) -> None:
        """Connect using HTTP/SSE transport."""
        # Use sse_client context manager
        self._session_context = sse_client(url=self.server_url)
        self._read, self._write = await self._session_context.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()

        # Initialize the session
        await self._session.initialize()

    async def _connect_stdio(self) -> None:
        """Connect using stdio transport."""
        # Extract command from stdio:// URL
        command = self.server_url.replace("stdio://", "")

        # Use stdio_client context manager
        server_params = StdioServerParameters(
            command=command,
            args=[],
        )
        self._session_context = stdio_client(server_params)
        self._read, self._write = await self._session_context.__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.__aenter__()

        # Initialize the session
        await self._session.initialize()

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self._session:
            try:
                logger.info("Disconnecting from MCP server")
                await self._session.__aexit__(None, None, None)
                if self._session_context:
                    await self._session_context.__aexit__(None, None, None)
                self._session = None
                self._connected = False
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
                self._connected = False

    async def call_tool(
        self, tool_name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments (optional)

        Returns:
            Tool response as a dictionary

        Raises:
            MCPError: If tool call fails
        """
        if not self._connected or not self._session:
            raise MCPError("Not connected to MCP server")

        try:
            logger.debug(f"Calling MCP tool: {tool_name} with args: {arguments}")

            # Call the tool using the MCP session
            result = await self._session.call_tool(
                name=tool_name, arguments=arguments or {}
            )

            logger.debug(f"Tool {tool_name} returned: {result}")

            # Convert result to dict format
            # MCP returns a CallToolResult object with content list
            if hasattr(result, "content"):
                return {"success": True, "content": result.content}
            else:
                return {"success": True, "result": str(result)}

        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            raise MCPError(f"Tool call failed: {e}") from e

    async def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available tools from the MCP server.

        Returns:
            List of tool descriptions

        Raises:
            MCPError: If listing fails
        """
        if not self._connected or not self._session:
            raise MCPError("Not connected to MCP server")

        try:
            result = await self._session.list_tools()

            # Convert to list of dicts
            tools = []
            for tool in result.tools:
                tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description if hasattr(tool, "description") else "",
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    }
                )

            return tools

        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            raise MCPError(f"Failed to list tools: {e}") from e

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected and self._session is not None

    @asynccontextmanager
    async def session(self):
        """
        Context manager for MCP session.

        Usage:
            async with client.session():
                await client.call_tool(...)
        """
        await self.connect()
        try:
            yield self
        finally:
            await self.disconnect()
