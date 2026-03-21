"""Shared validation helpers for Tower MCP tools."""

from typing import Any

MAX_BULK_DOMAINS = 100
MAX_CONCURRENCY = 50


def require_str(arguments: dict[str, Any], key: str) -> str:
    """Extract and validate a required string argument."""
    value = arguments.get(key)
    if not value or not isinstance(value, str):
        raise ValueError(f"Required argument '{key}' is missing or empty")
    return value


def require_domains(arguments: dict[str, Any]) -> list[str]:
    """Extract and validate a required domains list."""
    domains = arguments.get("domains")
    if not isinstance(domains, list) or len(domains) == 0:
        raise ValueError("'domains' must be a non-empty list")
    if len(domains) > MAX_BULK_DOMAINS:
        raise ValueError(f"'domains' list exceeds maximum of {MAX_BULK_DOMAINS}")
    for d in domains:
        if not isinstance(d, str) or not d.strip():
            raise ValueError("Each domain must be a non-empty string")
    return domains


def get_concurrency(arguments: dict[str, Any], default: int = 10) -> int:
    """Extract and validate an optional concurrency argument."""
    concurrency = arguments.get("concurrency", default)
    if not isinstance(concurrency, int) or concurrency < 1:
        raise ValueError("'concurrency' must be a positive integer")
    return min(concurrency, MAX_CONCURRENCY)
