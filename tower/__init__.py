"""Tower — unified MCP server for domain name utilities."""

try:
    from importlib.metadata import version

    __version__ = version("tower")
except Exception:
    __version__ = "0.1.0"
