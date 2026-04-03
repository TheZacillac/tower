"""Tower MCP server — unified entry point for Seer and Tome tools."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .tools import seer, tome

try:
    from arcanum._logging import configure_logging, set_correlation_id
    configure_logging("tower")
    _HAS_CORRELATION = True
except ImportError:
    _HAS_CORRELATION = False

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

    # Generate correlation ID for this tool call
    call_id = uuid.uuid4().hex[:8]
    if _HAS_CORRELATION:
        set_correlation_id(call_id)

    start = time.monotonic()
    logger.info("Tool call started: %s (call_id=%s)", name, call_id)

    try:
        result = await handler(name, arguments)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Tool call completed: %s (call_id=%s, elapsed_ms=%.1f)",
            name, call_id, elapsed_ms,
        )
        text = json.dumps(result, indent=2, default=str)
        return [TextContent(type="text", text=text)]
    except ValueError as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.warning(
            "Tool call invalid input: %s (call_id=%s, elapsed_ms=%.1f, error=%s)",
            name, call_id, elapsed_ms, e,
        )
        return [TextContent(type="text", text=f"Invalid input: {e}")]
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.exception(
            "Tool call failed: %s (call_id=%s, elapsed_ms=%.1f)",
            name, call_id, elapsed_ms,
        )
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
