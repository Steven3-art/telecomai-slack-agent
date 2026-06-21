"""
test_mcp_client.py — Quick test client for the TelecomAI MCP server
======================================================================
Run this WHILE mcp_server\server.py is running in another terminal.

Usage:
    python test_mcp_client.py
"""

import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    url = "http://localhost:8000/mcp"
    print(f"Connecting to {url} ...\n")

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List available tools
            tools = await session.list_tools()
            print("=== Available tools ===")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description.splitlines()[0]}")

            # 2. Call check_subscriber_status
            print("\n=== check_subscriber_status('222316544') ===")
            result1 = await session.call_tool(
                "check_subscriber_status", {"numero": "222316544"}
            )
            print(result1.content[0].text)

            # 3. Call get_connection_history
            print("\n=== get_connection_history('222302628', ['May 2026','June 2026']) ===")
            result2 = await session.call_tool(
                "get_connection_history",
                {"numero": "222302628", "months": ["May 2026", "June 2026"]}
            )
            print(result2.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
