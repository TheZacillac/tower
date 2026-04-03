"""Tome tool definitions and handlers for the Tower MCP server.

Provides reference database tools for TLD information, DNS record types,
and domain name industry glossary terms.
"""

import logging
import time
from typing import Any

import tome
from mcp.types import Tool

logger = logging.getLogger("tower.tools.tome")

from ._helpers import require_str


def _annotate_nulls(result: dict) -> dict:
    """Add a data-completeness note when null fields are present.

    Tome's database is still being populated. A null value means the data
    has not been collected yet — it must NOT be interpreted as false, 'no',
    or 'not required'.
    """
    null_fields = [k for k, v in result.items() if v is None]
    if null_fields:
        return {
            **result,
            "_data_completeness": (
                f"The following fields have no data yet and should be treated as "
                f"UNKNOWN (not as false or 'not required'): {', '.join(null_fields)}"
            ),
        }
    return result

TOOLS: list[Tool] = [
    Tool(
        name="tome_tld_lookup",
        description="Look up detailed information about a top-level domain (TLD). Returns type, registry, WHOIS server, RDAP URL, DNSSEC support, IDN support, restrictions, and delegation date. IMPORTANT: null values mean the data is not yet available in the database — they do NOT mean false, 'no', or 'not required'. Treat any null field as unknown/incomplete.",
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
    Tool(
        name="tome_tld_overview",
        description="Get a comprehensive overview of a TLD including registry operator, country mapping, WHOIS/RDAP servers, registration model, DNSSEC support, and transfer rules. Richer than tld_lookup. IMPORTANT: null values mean the data is not yet available in the database — they do NOT mean false, 'no', or 'not required'. Treat any null field as unknown/incomplete.",
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
        name="tome_tld_list_by_type",
        description="List all TLDs of a given type. Returns the full list of TLDs matching the specified category.",
        inputSchema={
            "type": "object",
            "properties": {
                "tld_type": {
                    "type": "string",
                    "enum": ["gTLD", "ccTLD", "nTLD"],
                    "description": "Type of TLD to list: gTLD (generic), ccTLD (country-code), or nTLD (new generic)",
                },
            },
            "required": ["tld_type"],
        },
    ),
    Tool(
        name="tome_tld_count",
        description="Return the total number of TLDs in the Tome reference database. Useful for understanding database coverage.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


async def handle(name: str, arguments: dict[str, Any]) -> Any:
    """Execute a Tome tool and return the result."""
    start = time.monotonic()
    logger.debug("Tome tool called: %s args=%s", name, list(arguments.keys()))

    match name:
        case "tome_tld_lookup":
            tld = require_str(arguments, "tld")
            raw = tome.tld_lookup(tld)
            if raw is None:
                result = {"error": f"No TLD found matching '{tld}'"}
            else:
                result = _annotate_nulls(raw)

        case "tome_tld_search":
            query = require_str(arguments, "query")
            result = tome.tld_search(query)

        case "tome_record_lookup":
            query = require_str(arguments, "query")
            raw = tome.record_lookup(query)
            if raw is None:
                result = {"error": f"No record type found matching '{query}'"}
            else:
                result = raw

        case "tome_record_search":
            query = require_str(arguments, "query")
            result = tome.record_search(query)

        case "tome_glossary_lookup":
            term = require_str(arguments, "term")
            raw = tome.glossary_lookup(term)
            if raw is None:
                result = {"error": f"No glossary term found matching '{term}'"}
            else:
                result = raw

        case "tome_glossary_search":
            query = require_str(arguments, "query")
            result = tome.glossary_search(query)

        case "tome_tld_overview":
            tld = require_str(arguments, "tld")
            raw = tome.tld_overview(tld)
            if raw is None:
                result = {"error": f"No TLD found matching '{tld}'"}
            else:
                result = _annotate_nulls(raw)

        case "tome_tld_list_by_type":
            tld_type = require_str(arguments, "tld_type")
            valid_tld_types = {"gTLD", "ccTLD", "nTLD"}
            if tld_type not in valid_tld_types:
                raise ValueError(f"'tld_type' must be one of: {', '.join(sorted(valid_tld_types))}")
            result = tome.tld_list_by_type(tld_type)

        case "tome_tld_count":
            result = {"count": tome.tld_count()}

        case _:
            raise ValueError(f"Unknown tome tool: {name}")

    elapsed = (time.monotonic() - start) * 1000
    logger.info("Tome tool completed: %s elapsed_ms=%.1f", name, elapsed)
    return result
