# CLAUDE.md - Tower

Tower is a unified MCP (Model Context Protocol) server that aggregates domain intelligence tools from Seer and Tome into a single entry point for AI assistants. It exposes 33 tools over stdio transport (24 Seer + 9 Tome). Seer surface tracks `seer>=0.24.0`.

---

## Architecture

```
tower/
├── pyproject.toml
├── .mcp.json               # MCP server launch config (uvx with local paths)
└── tower/
    ├── __init__.py          # Package version
    ├── server.py            # MCP server (tool registration, dispatch, entry point)
    └── tools/
        ├── __init__.py      # Tool module registry
        ├── _helpers.py      # Shared validation constants and functions
        ├── seer.py          # 24 Seer tool definitions + handler
        └── tome.py          # 9 Tome tool definitions + handler
```

Tower is a **thin orchestration layer** — it contains no business logic. All domain intelligence comes from the upstream Rust libraries (seer, tome) via their Python bindings.

---

## Tool Module Contract

Each tool module (`seer.py`, `tome.py`) must export:

1. **`TOOLS: list[Tool]`** — list of `mcp.types.Tool` definitions with JSON Schema input schemas
2. **`async handle(name: str, arguments: dict[str, Any]) -> Any`** — dispatcher that routes tool calls by name

### Adding a New Tool Module

1. Create `tower/tools/newmodule.py` exporting `TOOLS` and `handle()`
2. Import in `tower/tools/__init__.py`
3. Add to `_TOOL_MODULES` list in `server.py`

The server auto-discovers tools from all modules in `_TOOL_MODULES`.

---

## All 33 Tools

### Seer Tools (24)

**Single domain / lookup:**
| Tool | Input | Description |
|------|-------|-------------|
| `seer_lookup` | `domain` | Smart lookup (RDAP → WHOIS fallback) |
| `seer_info` | `domain` | Lightweight flat metadata summary |
| `seer_whois` | `domain` | WHOIS registration data |
| `seer_rdap` | `query` | Auto-routing RDAP (domain/IP/ASN) |
| `seer_rdap_domain` | `domain` | RDAP domain information |
| `seer_rdap_ip` | `ip` | RDAP IP address lookup |
| `seer_rdap_asn` | `asn` (int) | RDAP ASN lookup |
| `seer_availability` | `domain` | Registration availability with confidence |

**DNS:**
| Tool | Input | Description |
|------|-------|-------------|
| `seer_dig` | `domain`, `record_type?`, `nameserver?` | DNS query |
| `seer_propagation` | `domain`, `record_type?` | DNS propagation (29 servers) |
| `seer_dns_compare` | `domain`, `record_type`, `server_a`, `server_b` | Compare DNS between two nameservers |
| `seer_dns_follow` | `domain`, `record_type?`, `nameserver?`, `iterations?`, `interval_minutes?` | Monitor DNS changes over time |
| `seer_dnssec` | `domain` | DNSSEC chain validation |

**Security / health:**
| Tool | Input | Description |
|------|-------|-------------|
| `seer_status` | `domain` | Health check (HTTP, SSL, expiration) |
| `seer_ssl` | `domain` | TLS certificate analysis |
| `seer_subdomains` | `domain` | CT-log subdomain enumeration |
| `seer_diff` | `domain_a`, `domain_b` | Side-by-side domain comparison |

**Bulk operations:**
| Tool | Inputs | Description |
|------|--------|-------------|
| `seer_bulk_lookup` | `domains[]`, `concurrency?` | Bulk smart lookup |
| `seer_bulk_info` | `domains[]`, `concurrency?` | Bulk lightweight metadata |
| `seer_bulk_whois` | `domains[]`, `concurrency?` | Bulk WHOIS |
| `seer_bulk_dig` | `domains[]`, `record_type?`, `concurrency?` | Bulk DNS |
| `seer_bulk_status` | `domains[]`, `concurrency?` | Bulk health check |
| `seer_bulk_propagation` | `domains[]`, `record_type?`, `concurrency?` | Bulk propagation |
| `seer_bulk_availability` | `domains[]`, `concurrency?` | Bulk registration availability |

### Tome Tools (9)

| Tool | Input | Description |
|------|-------|-------------|
| `tome_tld_lookup` | `tld` | TLD details (type, registry, DNSSEC, restrictions) |
| `tome_tld_search` | `query` | Search TLDs by partial match |
| `tome_record_lookup` | `query` | DNS record type by name or code |
| `tome_record_search` | `query` | Search record types |
| `tome_glossary_lookup` | `term` | Domain industry term definition |
| `tome_glossary_search` | `query` | Search glossary |
| `tome_tld_overview` | `tld` | Comprehensive TLD overview (joins all data) |
| `tome_tld_list_by_type` | `tld_type` | List TLDs by type (gTLD, ccTLD, nTLD) |
| `tome_tld_count` | — | Total TLD count in database |

---

## Server Implementation (server.py)

### Dispatch Pattern

```python
_TOOL_MODULES = [seer, tome]
_HANDLERS: dict[str, Any] = {}

for _module in _TOOL_MODULES:
    for _tool in _module.TOOLS:
        _HANDLERS[_tool.name] = _module.handle
```

### MCP Handlers

- `list_tools()` — returns all Tool definitions from registered modules
- `call_tool(name, arguments)` — looks up handler, executes, returns JSON result

### Error Handling

Three-tier approach:
1. **Input validation** — `require_str()`, `require_domains()`, `get_concurrency()` raise `ValueError`
2. **ValueError** caught → returns `"Invalid input: {message}"`
3. **All other exceptions** logged with `logger.exception()` → returns generic error (no information leakage)

All results serialized as JSON with `default=str` for non-serializable objects.

### Entry Point

```bash
tower-mcp    # Runs MCP server on stdio
```

---

## Validation Helpers (_helpers.py)

**Constants:**
- `MAX_BULK_DOMAINS = 100`
- `MAX_CONCURRENCY = 50`

**Functions:**
- `require_str(arguments, key)` — validates required non-empty string
- `require_domains(arguments)` — validates domains list (non-empty, ≤100, all non-empty strings)
- `get_concurrency(arguments, default=10)` — validates and clamps to MAX_CONCURRENCY

---

## Async Execution

Seer tools use `loop.run_in_executor(None, seer.function, args)` to run blocking PyO3 calls without blocking the async event loop.

Tome tools call synchronously (fast in-memory lookups, no executor needed).

---

## MCP Configuration (.mcp.json)

```json
{
  "mcpServers": {
    "tower": {
      "command": "uvx",
      "args": [
        "--from", ".",
        "--with", "../seer/seer-py",
        "--with", "../tome/tome-py",
        "--with", "../scrolls",
        "tower-mcp"
      ]
    }
  }
}
```

Assumes sibling project layout under `arcanum_suite/`.

---

## Build & Test

```bash
pip install -e .
pytest

# Verify tools load
python -c "from tower.tools import seer, tome; print(len(seer.TOOLS + tome.TOOLS), 'tools')"
```

### Dependencies

- `mcp>=1.0` — Model Context Protocol SDK
- `seer>=0.24.0` — PyO3 bindings to Seer Rust library
- `tome>=0.1.0` — PyO3 bindings to Tome Rust library
- `scrolls>=0.1.0` — Skill definitions

Dev: `pytest>=7.0`, `pytest-asyncio>=0.21`

---

## Key Design Principles

1. **No business logic** — Tower routes to upstream libraries only
2. **Modular tools** — each source is a self-contained module with TOOLS + handle()
3. **Fail-safe errors** — never expose internal details to MCP clients
4. **Input validation** — type, constraint, and bounds checking before execution
5. **Async-safe** — blocking Rust FFI calls wrapped in executor
