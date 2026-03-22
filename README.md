# Tower

**A unified MCP server consolidating domain name utilities from [Seer](https://github.com/TheZacillac/seer) and [Tome](https://github.com/TheZacillac/tome).**

Tower provides a single MCP (Model Context Protocol) server that exposes tools from multiple domain name utility projects, giving AI assistants access to domain intelligence, DNS operations, and reference data through one entry point.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Available Tools](#available-tools)
  - [Seer Tools](#seer-tools)
  - [Tome Tools](#tome-tools)
- [Configuration](#configuration)
- [Adding Tool Modules](#adding-tool-modules)
- [Development](#development)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [License](#license)

---

## Features

| Feature | Description |
|---------|-------------|
| **Unified MCP Server** | Single server exposing tools from Seer and Tome through one connection |
| **Domain Intelligence** | WHOIS, RDAP, DNS, propagation, and status checks via Seer |
| **Reference Data** | TLD info, DNS record type definitions, and glossary terms via Tome |
| **Bundled Skills** | Installs [Scrolls](https://github.com/TheZacillac/scrolls) — AI agent skill definitions for Seer and Tome |
| **Bulk Operations** | Process up to 100 domains concurrently for any Seer operation |
| **Modular Design** | Each tool source is an independent module — easy to add, remove, or update |
| **19 Tools** | 13 Seer tools + 6 Tome tools registered through a single dispatch table |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         tower-mcp                           │
│                    (MCP Server · stdio)                      │
├─────────────────────────────┬───────────────────────────────┤
│      tower/tools/seer.py    │      tower/tools/tome.py      │
│       (13 tools)            │        (6 tools)              │
└──────────┬──────────────────┴──────────────┬────────────────┘
           │                                 │
           ▼                                 ▼
┌─────────────────────┐          ┌─────────────────────┐
│     seer (Python)   │          │     tome (Python)    │
│    PyO3 bindings    │          │    PyO3 bindings     │
└──────────┬──────────┘          └──────────┬──────────┘
           │                                 │
           ▼                                 ▼
┌─────────────────────┐          ┌─────────────────────┐
│     seer-core       │          │     tome-core        │
│   (Rust library)    │          │   (Rust library)     │
└─────────────────────┘          └─────────────────────┘
```

Tower is a thin orchestration layer. All business logic lives in the upstream Rust core libraries; Tower simply registers their Python-exposed functions as MCP tools and routes calls to the appropriate handler.

---

## Installation

### Prerequisites

- Python 3.9+
- [Seer Python bindings](https://github.com/TheZacillac/seer) (seer-py) built and available
- [Tome Python bindings](https://github.com/TheZacillac/tome) (tome-py) built and available
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### From Source

```bash
# Clone the repository
git clone https://github.com/TheZacillac/tower.git
cd tower

# Install with dependencies (assumes seer-py and tome-py are already built)
uv pip install -e .
```

If the seer, tome, and scrolls packages are not published to PyPI, install them from their local paths:

```bash
uv pip install \
    -e /path/to/seer/seer-py \
    -e /path/to/tome/tome-py \
    -e /path/to/scrolls \
    -e .
```

This installs the MCP tools (seer, tome), the AI agent skills (scrolls), and Tower itself.

### Using uvx (No Install Required)

```bash
uvx --from /path/to/tower \
    --with /path/to/seer/seer-py \
    --with /path/to/tome/tome-py \
    --with /path/to/scrolls \
    tower-mcp
```

---

## Usage

### Starting the Server

```bash
tower-mcp
```

The server runs on stdio transport, communicating via stdin/stdout using the Model Context Protocol.

### Claude Code Integration

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "tower": {
      "command": "uvx",
      "args": [
        "--from", "/path/to/tower",
        "--with", "/path/to/seer/seer-py",
        "--with", "/path/to/tome/tome-py",
        "--with", "/path/to/scrolls",
        "tower-mcp"
      ]
    }
  }
}
```

### Claude Desktop Integration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tower": {
      "command": "tower-mcp"
    }
  }
}
```

---

## Available Tools

### Seer Tools

Domain intelligence operations powered by [Seer](https://github.com/TheZacillac/seer).

#### Single Domain

| Tool | Description |
|------|-------------|
| `seer_lookup` | Smart lookup — tries RDAP first, falls back to WHOIS |
| `seer_whois` | WHOIS registration data |
| `seer_rdap_domain` | RDAP domain lookup |
| `seer_rdap_ip` | RDAP IP address lookup |
| `seer_rdap_asn` | RDAP Autonomous System Number lookup |
| `seer_dig` | DNS record query (A, AAAA, MX, TXT, NS, SOA, CNAME, CAA, PTR, SRV, ANY) |
| `seer_propagation` | DNS propagation check across 29 global nameservers |
| `seer_status` | Domain health check (HTTP, SSL, expiration) |

#### Bulk Operations

| Tool | Description |
|------|-------------|
| `seer_bulk_lookup` | Smart lookup for multiple domains |
| `seer_bulk_whois` | WHOIS lookup for multiple domains |
| `seer_bulk_dig` | DNS query for multiple domains |
| `seer_bulk_status` | Health check for multiple domains |
| `seer_bulk_propagation` | Propagation check for multiple domains |

**Bulk limits:** max 100 domains per request, max 50 concurrent operations.

### Tome Tools

Reference database lookups powered by [Tome](https://github.com/TheZacillac/tome).

| Tool | Description |
|------|-------------|
| `tome_tld_lookup` | Look up a TLD — type, registry, WHOIS/RDAP servers, DNSSEC, restrictions |
| `tome_tld_search` | Search TLDs by partial match |
| `tome_record_lookup` | Look up a DNS record type by name or numeric code |
| `tome_record_search` | Search DNS record types by partial match |
| `tome_glossary_lookup` | Look up a domain industry term or abbreviation |
| `tome_glossary_search` | Search glossary terms by partial match |

---

## Configuration

Tower has no configuration of its own. Tool behavior is determined by the upstream libraries:

| Setting | Source | Default |
|---------|--------|---------|
| Bulk domain limit | Tower | 100 |
| Max concurrency | Tower | 50 |
| WHOIS timeout | Seer | 10 seconds |
| RDAP timeout | Seer | 30 seconds |
| DNS timeout | Seer | 5 seconds |

---

## Adding Tool Modules

Tower is designed to make adding new tool sources straightforward. Each module follows a simple contract:

1. Create a new file in `tower/tools/` (e.g., `tower/tools/newmodule.py`)
2. Export a `TOOLS` list of `mcp.types.Tool` definitions
3. Export a `handle(name, arguments)` async function
4. Import the module in `tower/tools/__init__.py`

### Module Template

```python
"""Tool definitions and handlers for NewModule."""

from typing import Any
from mcp.types import Tool

TOOLS: list[Tool] = [
    Tool(
        name="newmodule_example",
        description="Description of what this tool does.",
        inputSchema={
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "Parameter description",
                },
            },
            "required": ["param"],
        },
    ),
]


async def handle(name: str, arguments: dict[str, Any]) -> Any:
    """Execute a NewModule tool and return the result."""
    match name:
        case "newmodule_example":
            # Call your library function here
            ...
        case _:
            raise ValueError(f"Unknown tool: {name}")
```

The server automatically discovers all tools via the `_TOOL_MODULES` list in `server.py` and builds a dispatch table at import time. No changes to `server.py` are needed beyond adding your module to that list.

---

## Development

### Setup

```bash
git clone https://github.com/TheZacillac/tower.git
cd tower

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install \
    -e /path/to/seer/seer-py \
    -e /path/to/tome/tome-py \
    -e /path/to/scrolls \
    -e ".[dev]"
```

### Running Tests

```bash
pytest
```

### Verifying the Server

```bash
# Check that all tools load without errors
python -c "from tower.server import mcp; print('OK')"

# List all registered tools
python -c "
from tower.tools import seer, tome
for t in seer.TOOLS + tome.TOOLS:
    print(f'  {t.name}')
"
```

---

## Project Structure

```
tower/
├── README.md               # This file
├── pyproject.toml           # Package configuration and entry points
├── .mcp.json                # MCP server launch configuration
├── .gitignore
└── tower/
    ├── __init__.py          # Package metadata
    ├── server.py            # MCP server — tool registration and call routing
    └── tools/
        ├── __init__.py      # Tool module registry
        ├── _helpers.py      # Shared validation (require_str, require_domains, etc.)
        ├── seer.py          # Seer tool definitions and handlers (13 tools)
        └── tome.py          # Tome tool definitions and handlers (6 tools)
```

---

## Technology Stack

| Dependency | Purpose |
|------------|---------|
| [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) | Model Context Protocol server framework |
| [Seer](https://github.com/TheZacillac/seer) | Domain intelligence (WHOIS, RDAP, DNS, status) |
| [Tome](https://github.com/TheZacillac/tome) | Reference data (TLDs, record types, glossary) |
| [Scrolls](https://github.com/TheZacillac/scrolls) | AI agent skill definitions for Seer and Tome |
| [Hatchling](https://hatch.pypa.io/) | Python build backend |

---

## License

MIT License

Copyright (c) 2026 Zac Roach

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
