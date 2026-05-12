"""Seer tool definitions and handlers for the Tower MCP server.

Provides domain intelligence tools: WHOIS, RDAP, DNS, propagation, status,
availability, subdomains, SSL/DNSSEC, DNS comparison/monitoring, diff, info,
and bulk variants.

Tool set tracks seer>=0.24.0 public API.
"""

import asyncio
import ipaddress
import logging
import time
from typing import Any

import seer
from mcp.types import Tool

from ._helpers import (
    MAX_BULK_DOMAINS,
    MAX_CONCURRENCY,
    get_concurrency,
    require_domains,
    require_str,
)

logger = logging.getLogger("tower.tools.seer")

VALID_RECORD_TYPES = {"A", "AAAA", "MX", "TXT", "NS", "SOA", "CNAME", "CAA", "PTR", "SRV", "ANY"}

# Upper bounds for dns_follow to protect the shared Tokio runtime / event loop.
# Seer's Rust side allows up to 100 iterations and 60 total minutes; we use
# tighter caps here because MCP tool calls block the server for the full run.
MAX_FOLLOW_ITERATIONS = 20
MAX_FOLLOW_INTERVAL_MINUTES = 10.0


def _validate_record_type(record_type: str) -> str:
    """Validate and normalize a DNS record type string."""
    rt = record_type.strip().upper()
    if rt not in VALID_RECORD_TYPES:
        raise ValueError(f"'record_type' must be one of: {', '.join(sorted(VALID_RECORD_TYPES))}")
    return rt


def _validate_ip(ip: str) -> str:
    """Validate that `ip` parses as an IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(ip)
    except ValueError as e:
        raise ValueError(f"'ip' must be a valid IPv4 or IPv6 address (got {ip!r})") from e
    return ip


def _validate_asn(asn: Any) -> int:
    """Validate that `asn` is an integer in the valid 32-bit ASN range."""
    if isinstance(asn, bool) or not isinstance(asn, int) or asn < 0 or asn > 4294967295:
        raise ValueError(f"'asn' must be an integer between 0 and 4294967295 (got {asn!r})")
    return asn


def _validate_follow_params(iterations: Any, interval_minutes: Any) -> tuple[int, float]:
    """Validate dns_follow iteration count and interval."""
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise ValueError("'iterations' must be a positive integer")
    if iterations > MAX_FOLLOW_ITERATIONS:
        raise ValueError(f"'iterations' must be <= {MAX_FOLLOW_ITERATIONS}")
    if not isinstance(interval_minutes, (int, float)) or isinstance(interval_minutes, bool):
        raise ValueError("'interval_minutes' must be a number")
    interval = float(interval_minutes)
    if interval <= 0 or interval > MAX_FOLLOW_INTERVAL_MINUTES:
        raise ValueError(
            f"'interval_minutes' must be between 0 (exclusive) and {MAX_FOLLOW_INTERVAL_MINUTES}"
        )
    return iterations, interval


TOOLS: list[Tool] = [
    # ── Single-domain lookups ────────────────────────────────────────────
    Tool(
        name="seer_lookup",
        description="Smart domain lookup that tries RDAP first (modern protocol with structured data) and falls back to WHOIS if RDAP is unavailable. Returns registration data with source indicator.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to look up (e.g., 'example.com')",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_info",
        description="Lightweight domain metadata summary. Returns a flat, registrar-agnostic view (domain, registrar, creation/expiration dates, nameservers, status) derived from the smart lookup. Cheaper and simpler than seer_lookup when you only need a summary.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to look up (e.g., 'example.com')",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_whois",
        description="Look up WHOIS information for a domain name. Returns registrar, creation date, expiration date, nameservers, and status information.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to look up (e.g., 'example.com')",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_rdap",
        description="Auto-routing RDAP lookup for a domain, IPv4/IPv6 address, or ASN. Classifies the query in Rust so domains starting with 'AS' (e.g. as1234.io) are not misrouted to the ASN endpoint. Use this when the query type is not known in advance.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Domain, IP address, or ASN (e.g., 'example.com', '8.8.8.8', 'AS15169')",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="seer_rdap_domain",
        description="Look up RDAP (Registration Data Access Protocol) information for a domain. Returns structured registration data including registrar, dates, nameservers, and DNSSEC status.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to look up",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_rdap_ip",
        description="Look up RDAP information for an IP address. Returns network registration information including the network range, country, and responsible organization.",
        inputSchema={
            "type": "object",
            "properties": {
                "ip": {
                    "type": "string",
                    "description": "IP address (IPv4 or IPv6) to look up",
                },
            },
            "required": ["ip"],
        },
    ),
    Tool(
        name="seer_rdap_asn",
        description="Look up RDAP information for an Autonomous System Number (ASN). Returns organization and network range information.",
        inputSchema={
            "type": "object",
            "properties": {
                "asn": {
                    "type": "integer",
                    "description": "AS number (e.g., 15169 for Google)",
                    "minimum": 0,
                    "maximum": 4294967295,
                },
            },
            "required": ["asn"],
        },
    ),
    Tool(
        name="seer_dig",
        description="Query DNS records for a domain, similar to the 'dig' command. Supports all major record types.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to query",
                },
                "record_type": {
                    "type": "string",
                    "description": "DNS record type (A, AAAA, MX, TXT, NS, SOA, CNAME, CAA, PTR, SRV, ANY)",
                    "default": "A",
                },
                "nameserver": {
                    "type": "string",
                    "description": "Optional nameserver IP to query (e.g., '8.8.8.8')",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_propagation",
        description="Check DNS propagation for a domain across multiple global DNS servers. Shows which servers have the record and identifies inconsistencies.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to check",
                },
                "record_type": {
                    "type": "string",
                    "description": "DNS record type to check (default: A)",
                    "default": "A",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_status",
        description="Check the health status of a domain including HTTP accessibility, SSL certificate validity, and domain expiration.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to check (e.g., 'example.com')",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_availability",
        description="Check whether a domain is available for registration. Returns an availability decision with confidence level and the detection method used (RDAP / WHOIS / DNS heuristics).",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain name to check for availability",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_subdomains",
        description="Enumerate subdomains of a domain using Certificate Transparency logs. Returns the set of discovered subdomain names with a total count.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Apex domain to enumerate (e.g., 'example.com')",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_ssl",
        description="Analyze the SSL/TLS certificate presented by a domain on port 443. Returns issuer, subject, validity window, days to expiry, subject alternative names (SANs), signature algorithm, and protocol details.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain whose TLS certificate to inspect",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_dnssec",
        description="Check DNSSEC configuration for a domain. Returns DS and DNSKEY records, validation chain status, and any problems detected (missing DS, broken chain, algorithm issues).",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to check",
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_dns_compare",
        description="Compare DNS records for a domain between two specific nameservers. Returns matching records, differences, and records unique to each server — useful for debugging authoritative-vs-resolver drift or nameserver migration.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to query",
                },
                "record_type": {
                    "type": "string",
                    "description": "DNS record type to compare (A, AAAA, MX, TXT, NS, SOA, CNAME, CAA, PTR, SRV, ANY)",
                },
                "server_a": {
                    "type": "string",
                    "description": "First nameserver (IP or hostname)",
                },
                "server_b": {
                    "type": "string",
                    "description": "Second nameserver (IP or hostname)",
                },
            },
            "required": ["domain", "record_type", "server_a", "server_b"],
        },
    ),
    Tool(
        name="seer_dns_follow",
        description="Monitor a DNS record over time by querying it repeatedly at a fixed interval. Returns the timeline of responses and flags changes between iterations. BLOCKS the server for iterations * interval_minutes — keep the total modest.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Domain to monitor",
                },
                "record_type": {
                    "type": "string",
                    "description": "DNS record type (default: A)",
                    "default": "A",
                },
                "nameserver": {
                    "type": "string",
                    "description": "Optional nameserver to query",
                },
                "iterations": {
                    "type": "integer",
                    "description": f"Number of queries (default: 3, max: {MAX_FOLLOW_ITERATIONS})",
                    "default": 3,
                    "minimum": 1,
                    "maximum": MAX_FOLLOW_ITERATIONS,
                },
                "interval_minutes": {
                    "type": "number",
                    "description": f"Minutes between queries (default: 1.0, max: {MAX_FOLLOW_INTERVAL_MINUTES})",
                    "default": 1.0,
                },
            },
            "required": ["domain"],
        },
    ),
    Tool(
        name="seer_diff",
        description="Compare two domains side-by-side across registration, DNS records, and SSL certificates. Highlights differences in registrar, creation/expiration, nameservers, A records, and certificate fingerprint/issuer.",
        inputSchema={
            "type": "object",
            "properties": {
                "domain_a": {
                    "type": "string",
                    "description": "First domain",
                },
                "domain_b": {
                    "type": "string",
                    "description": "Second domain",
                },
            },
            "required": ["domain_a", "domain_b"],
        },
    ),
    # ── Bulk operations ──────────────────────────────────────────────────
    Tool(
        name="seer_bulk_lookup",
        description="Smart lookup for multiple domains at once (tries RDAP first, falls back to WHOIS). Efficient for checking many domains.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to look up",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 10, max: {MAX_CONCURRENCY})",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="seer_bulk_info",
        description="Lightweight bulk metadata lookup for multiple domains. Returns the flat domain-info summary (registrar, dates, nameservers, status) for each — cheaper than seer_bulk_lookup when you only need a summary.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to look up",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 10, max: {MAX_CONCURRENCY})",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="seer_bulk_whois",
        description="Look up WHOIS information for multiple domains at once. Efficient for checking many domains.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to look up",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 10, max: {MAX_CONCURRENCY})",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="seer_bulk_dig",
        description="Query DNS records for multiple domains at once.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to query",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "record_type": {
                    "type": "string",
                    "description": "DNS record type (default: A)",
                    "default": "A",
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 10, max: {MAX_CONCURRENCY})",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="seer_bulk_status",
        description="Check health status for multiple domains at once. Returns HTTP, SSL, and expiration status for each domain.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to check",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 10, max: {MAX_CONCURRENCY})",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="seer_bulk_propagation",
        description="Check DNS propagation for multiple domains at once across global DNS servers.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to check",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "record_type": {
                    "type": "string",
                    "description": "DNS record type to check (default: A)",
                    "default": "A",
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 5, max: {MAX_CONCURRENCY})",
                    "default": 5,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
    Tool(
        name="seer_bulk_availability",
        description="Check registration availability for multiple domains at once. Each result includes an availability decision, confidence level, and detection method.",
        inputSchema={
            "type": "object",
            "properties": {
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domain names to check",
                    "maxItems": MAX_BULK_DOMAINS,
                },
                "concurrency": {
                    "type": "integer",
                    "description": f"Number of concurrent requests (default: 10, max: {MAX_CONCURRENCY})",
                    "default": 10,
                    "minimum": 1,
                    "maximum": MAX_CONCURRENCY,
                },
            },
            "required": ["domains"],
        },
    ),
]


async def handle(name: str, arguments: dict[str, Any]) -> Any:
    """Execute a Seer tool and return the result."""
    start = time.monotonic()
    logger.debug("Seer tool called: %s args=%s", name, list(arguments.keys()))
    loop = asyncio.get_running_loop()

    match name:
        case "seer_lookup":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.lookup, domain)

        case "seer_info":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.info, domain)

        case "seer_whois":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.whois, domain)

        case "seer_rdap":
            query = require_str(arguments, "query")
            result = await loop.run_in_executor(None, seer.rdap, query)

        case "seer_rdap_domain":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.rdap_domain, domain)

        case "seer_rdap_ip":
            ip = _validate_ip(require_str(arguments, "ip"))
            result = await loop.run_in_executor(None, seer.rdap_ip, ip)

        case "seer_rdap_asn":
            asn = _validate_asn(arguments.get("asn"))
            result = await loop.run_in_executor(None, seer.rdap_asn, asn)

        case "seer_dig":
            domain = require_str(arguments, "domain")
            record_type = _validate_record_type(arguments.get("record_type", "A"))
            nameserver = arguments.get("nameserver")
            if nameserver is not None and not isinstance(nameserver, str):
                raise ValueError("'nameserver' must be a string if provided")
            result = await loop.run_in_executor(
                None, seer.dig, domain, record_type, nameserver
            )

        case "seer_propagation":
            domain = require_str(arguments, "domain")
            record_type = _validate_record_type(arguments.get("record_type", "A"))
            result = await loop.run_in_executor(
                None, seer.propagation, domain, record_type
            )

        case "seer_status":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.status, domain)

        case "seer_availability":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.availability, domain)

        case "seer_subdomains":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.subdomains, domain)

        case "seer_ssl":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.ssl, domain)

        case "seer_dnssec":
            domain = require_str(arguments, "domain")
            result = await loop.run_in_executor(None, seer.dnssec, domain)

        case "seer_dns_compare":
            domain = require_str(arguments, "domain")
            record_type = _validate_record_type(require_str(arguments, "record_type"))
            server_a = require_str(arguments, "server_a")
            server_b = require_str(arguments, "server_b")
            result = await loop.run_in_executor(
                None, seer.dns_compare, domain, record_type, server_a, server_b
            )

        case "seer_dns_follow":
            domain = require_str(arguments, "domain")
            record_type = _validate_record_type(arguments.get("record_type", "A"))
            nameserver = arguments.get("nameserver")
            if nameserver is not None and not isinstance(nameserver, str):
                raise ValueError("'nameserver' must be a string if provided")
            iterations, interval_minutes = _validate_follow_params(
                arguments.get("iterations", 3),
                arguments.get("interval_minutes", 1.0),
            )
            result = await loop.run_in_executor(
                None,
                seer.dns_follow,
                domain,
                record_type,
                nameserver,
                iterations,
                interval_minutes,
            )

        case "seer_diff":
            domain_a = require_str(arguments, "domain_a")
            domain_b = require_str(arguments, "domain_b")
            result = await loop.run_in_executor(None, seer.diff, domain_a, domain_b)

        case "seer_bulk_lookup":
            domains = require_domains(arguments)
            concurrency = get_concurrency(arguments, default=10)
            result = await loop.run_in_executor(
                None, seer.bulk_lookup, domains, concurrency
            )

        case "seer_bulk_info":
            domains = require_domains(arguments)
            concurrency = get_concurrency(arguments, default=10)
            result = await loop.run_in_executor(
                None, seer.bulk_info, domains, concurrency
            )

        case "seer_bulk_whois":
            domains = require_domains(arguments)
            concurrency = get_concurrency(arguments, default=10)
            result = await loop.run_in_executor(
                None, seer.bulk_whois, domains, concurrency
            )

        case "seer_bulk_dig":
            domains = require_domains(arguments)
            record_type = _validate_record_type(arguments.get("record_type", "A"))
            concurrency = get_concurrency(arguments, default=10)
            result = await loop.run_in_executor(
                None, seer.bulk_dig, domains, record_type, concurrency
            )

        case "seer_bulk_status":
            domains = require_domains(arguments)
            concurrency = get_concurrency(arguments, default=10)
            result = await loop.run_in_executor(
                None, seer.bulk_status, domains, concurrency
            )

        case "seer_bulk_propagation":
            domains = require_domains(arguments)
            record_type = _validate_record_type(arguments.get("record_type", "A"))
            concurrency = get_concurrency(arguments, default=5)
            result = await loop.run_in_executor(
                None, seer.bulk_propagation, domains, record_type, concurrency
            )

        case "seer_bulk_availability":
            domains = require_domains(arguments)
            concurrency = get_concurrency(arguments, default=10)
            result = await loop.run_in_executor(
                None, seer.bulk_availability, domains, concurrency
            )

        case _:
            raise ValueError(f"Unknown seer tool: {name}")

    elapsed = (time.monotonic() - start) * 1000
    logger.info("Seer tool completed: %s elapsed_ms=%.1f", name, elapsed)
    return result
