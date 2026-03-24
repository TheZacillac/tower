"""Tower MCP server — unified entry point for Seer and Tome tools."""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools import seer, tome

logger = logging.getLogger(__name__)

mcp = Server("tower")

# Collect all tools and build a dispatch table mapping tool names to their handler.
_TOOL_MODULES = [seer, tome]
_HANDLERS: dict[str, Any] = {}

for _module in _TOOL_MODULES:
    for _tool in _module.TOOLS:
        _HANDLERS[_tool.name] = _module.handle


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools from every registered module."""
    tools: list[Tool] = []
    for module in _TOOL_MODULES:
        tools.extend(module.TOOLS)
    return tools


@mcp.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Route a tool call to the appropriate module handler."""
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    # Normalize None arguments to empty dict (MCP SDK may pass None)
    arguments = arguments or {}

    try:
        result = await handler(name, arguments)
        text = json.dumps(result, indent=2, default=str)
        return [TextContent(type="text", text=text)]
    except ValueError as e:
        return [TextContent(type="text", text=f"Invalid input: {e}")]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text="An internal error occurred while processing your request.")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


def run():
    """Entry point for the MCP server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
