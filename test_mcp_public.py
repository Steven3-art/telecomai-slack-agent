import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = "https://7382-154-72-161-38.ngrok-free.app/mcp"
    print(f"Connecting to {url} ...\n")
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("=== Available tools ===")
            for t in tools.tools:
                print(f"  - {t.name}")
            result = await session.call_tool(
                "check_subscriber_status", {"numero": "222230906"}
            )
            print(result.content[0].text)

if __name__ == "__main__":
    asyncio.run(main())