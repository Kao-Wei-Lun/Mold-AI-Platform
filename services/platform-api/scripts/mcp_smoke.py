"""Protocol-level MCP preflight for the local Demo gateway."""

from __future__ import annotations

import argparse
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

REQUIRED_TOOLS = {
    "search_similar_molds",
    "get_similarity_explanation",
    "run_design_review",
    "get_job_status",
    "search_knowledge",
}


async def inspect_gateway(url: str) -> None:
    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            catalog = await session.list_tools()
            tools = {tool.name: tool for tool in catalog.tools}
            missing = REQUIRED_TOOLS - set(tools)
            if missing:
                raise RuntimeError(f"Missing MCP tools: {', '.join(sorted(missing))}")
            for name in REQUIRED_TOOLS:
                tool = tools[name]
                if not tool.input_schema or not tool.output_schema or tool.annotations is None:
                    raise RuntimeError(f"Incomplete schema or annotations for MCP tool: {name}")
            result = await session.call_tool(
                "search_knowledge", {"query": "rib thickness", "top_k": 3}
            )
            if result.is_error or not result.structured_content:
                raise RuntimeError("search_knowledge MCP smoke call failed")
            print(
                f"MCP {initialized.server_info.name}@{initialized.server_info.version}: "
                f"{len(tools)} tools discovered; search_knowledge call succeeded."
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://mcp-gateway:8001/mcp")
    args = parser.parse_args()
    asyncio.run(inspect_gateway(args.url))


if __name__ == "__main__":
    main()
