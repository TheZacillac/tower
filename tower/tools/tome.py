"""Tome tool definitions and handlers for the Tower MCP server.

Provides reference database tools for TLD information, DNS record types,
and domain name industry glossary terms.
"""

from typing import Any

import tome
from mcp.types import Tool

from ._helpers import require_str

TOOLS: list[Tool] = [
    Tool(
        name="tome_tld_lookup",
        description="Look up detailed information about a top-level domain (TLD). Returns type, registry, WHOIS server, RDAP URL, DNSSEC support, IDN support, restrictions, and delegation date.",
        inputSchema={
            "type": "object",
            "properties": {
                "tld": {
                    "type": "string",
                    "description": "TLD to look up (e.g., 'com', 'uk', 'app'). Do not include the leading dot.",
                },
            },
            "required": ["tld"],
        },
    ),
    Tool(
        name="tome_tld_search",
        description="Search for TLDs by partial match. Useful for finding TLDs related to a keyword or discovering available TLD options.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to match against TLD names, registries, and descriptions",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="tome_record_lookup",
        description="Look up detailed information about a DNS record type by name or numeric code. Returns type code, description, RDATA format, example, defining RFCs, status, and related types.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Record type name (e.g., 'A', 'MX', 'CNAME') or numeric type code (e.g., '1', '15')",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="tome_record_search",
        description="Search for DNS record types by partial match. Useful for finding record types related to a particular function or feature.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to match against record type names, summaries, and descriptions",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="tome_glossary_lookup",
        description="Look up a domain name industry term or abbreviation. Returns the definition, category, related terms, and references.",
        inputSchema={
            "type": "object",
            "properties": {
                "term": {
                    "type": "string",
                    "description": "Term or abbreviation to look up (e.g., 'DNSSEC', 'registrar', 'EPP')",
                },
            },
            "required": ["term"],
        },
    ),
    Tool(
        name="tome_glossary_search",
        description="Search the domain name industry glossary by partial match. Useful for finding terminology related to a specific topic.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to match against terms, abbreviations, and definitions",
                },
            },
            "required": ["query"],
        },
    ),
]


async def handle(name: str, arguments: dict[str, Any]) -> Any:
    """Execute a Tome tool and return the result."""
    match name:
        case "tome_tld_lookup":
            tld = require_str(arguments, "tld")
            result = tome.tld_lookup(tld)
            if result is None:
                return {"error": f"No TLD found matching '{tld}'"}
            return result

        case "tome_tld_search":
            query = require_str(arguments, "query")
            return tome.tld_search(query)

        case "tome_record_lookup":
            query = require_str(arguments, "query")
            result = tome.record_lookup(query)
            if result is None:
                return {"error": f"No record type found matching '{query}'"}
            return result

        case "tome_record_search":
            query = require_str(arguments, "query")
            return tome.record_search(query)

        case "tome_glossary_lookup":
            term = require_str(arguments, "term")
            result = tome.glossary_lookup(term)
            if result is None:
                return {"error": f"No glossary term found matching '{term}'"}
            return result

        case "tome_glossary_search":
            query = require_str(arguments, "query")
            return tome.glossary_search(query)

        case _:
            raise ValueError(f"Unknown tome tool: {name}")
