#!/usr/bin/env python3
"""
Quick test script to diagnose MCP connection issues.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from conductor.mcp.client import MCPClient, MCPConnectionError


async def test_connection(url: str):
    """Test MCP connection with detailed output."""
    print(f"\n{'='*70}")
    print(f"Testing MCP Connection")
    print(f"{'='*70}\n")
    print(f"Target URL: {url}\n")

    # Test 1: Basic connection
    print("Test 1: Creating MCP client...")
    client = MCPClient(server_url=url, timeout=10.0, max_retries=1)
    print(f"  ✓ Client created\n")

    # Test 2: Attempting connection
    print("Test 2: Attempting to connect...")
    try:
        await client.connect()
        print(f"  ✓ Connected successfully!\n")

        # Test 3: List available tools
        print("Test 3: Listing available tools...")
        try:
            tools = await client.list_tools()
            print(f"  ✓ Found {len(tools)} tools:")
            for tool in tools[:5]:
                print(f"    - {tool['name']}: {tool.get('description', 'No description')[:60]}")
            if len(tools) > 5:
                print(f"    ... and {len(tools) - 5} more")
            print()

        except Exception as e:
            print(f"  ✗ Failed to list tools: {e}\n")

        # Cleanup
        print("Cleaning up...")
        await client.disconnect()
        print("  ✓ Disconnected\n")

        return True

    except MCPConnectionError as e:
        print(f"  ✗ Connection failed: {e}\n")

        # Provide troubleshooting
        print("Troubleshooting tips:")
        print("  1. Verify the MCP server is running:")
        print("     npx @playwright/mcp@latest --port 8931 --host 0.0.0.0")
        print()
        print("  2. Check if the server is accessible:")
        print(f"     curl -v {url}")
        print()
        print("  3. Verify the URL format:")
        print("     ✓ Correct: http://host:port/sse")
        print("     ✗ Wrong:   http://host:port/mcp")
        print()

        return False

    except Exception as e:
        print(f"  ✗ Unexpected error: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Default to common configurations
        print("Usage: python test_mcp_connection.py <url>")
        print("\nTesting common configurations...\n")

        test_urls = [
            "http://localhost:8931/sse",
            "http://192.168.1.5:8931/sse",
        ]

        for url in test_urls:
            success = await test_connection(url)
            if success:
                print(f"\n{'='*70}")
                print(f"✓ SUCCESS: Connection to {url} works!")
                print(f"{'='*70}\n")
                return
            print()

        print(f"\n{'='*70}")
        print(f"✗ FAILED: None of the test URLs worked")
        print(f"{'='*70}\n")
        return

    # Single URL test
    success = await test_connection(url)
    if success:
        print(f"\n{'='*70}")
        print(f"✓ SUCCESS: Connection works!")
        print(f"{'='*70}\n")
    else:
        print(f"\n{'='*70}")
        print(f"✗ FAILED: Connection did not work")
        print(f"{'='*70}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
