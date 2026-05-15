"""Connect to MCP servers and expose their tools to LangChain.

THIS IS THE SPINE OF DATAPILOT.

Tools are NOT defined in our codebase. They live in MCP servers:

    mcp.json
       |
       +-- shopflow-sqlite   -- off the shelf (Anthropic's mcp-server-sqlite)
       +-- datapilot-dq      -- our own (Module 07)

We spawn each server as a subprocess (stdio transport) and ask it
"what tools do you have?" — that's the entire integration. No imports
from a tools module. No bound functions. The LLM gets whatever the MCP
servers offer, with zero code on our side per tool.

In production: same pattern, plus real auth, transport, monitoring.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

CONFIG_PATH = Path(__file__).parent / "config" / "mcp.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_RX = re.compile(r"\$\{([^}]+)\}")


def _load_config() -> dict:
    """Load mcp.json and substitute ${ENV_VAR} placeholders.

    Path-like env vars are resolved to absolute paths against the repo root,
    so the spawned MCP subprocess gets a correct path regardless of its cwd.
    """
    # Make SHOPFLOW_DB absolute before substitution (subprocess cwd may differ).
    db = os.getenv("SHOPFLOW_DB", "data/shopflow.db")
    if not Path(db).is_absolute():
        os.environ["SHOPFLOW_DB"] = str((REPO_ROOT / db).resolve())

    text = CONFIG_PATH.read_text()
    # On Windows, JSON requires backslashes to be escaped.
    def _sub(m: re.Match) -> str:
        v = os.getenv(m.group(1), m.group(0))
        return v.replace("\\", "\\\\")
    text = ENV_RX.sub(_sub, text)
    return json.loads(text)


async def _gather():
    cfg = _load_config()
    servers = cfg["mcpServers"]
    # Make sure subprocesses use THIS interpreter (with our venv's deps),
    # not whatever `python` happens to resolve to on PATH.
    import sys as _sys
    for name, spec in servers.items():
        if spec.get("command") == "python":
            spec["command"] = _sys.executable
    client = MultiServerMCPClient(servers)
    tools = await client.get_tools()
    return client, tools


def load_mcp_tools() -> tuple[MultiServerMCPClient, list]:
    """Synchronous entry point. Spawns MCP servers and returns their tools.

    Returns:
        (client, tools) — keep `client` alive for the lifetime of the app
        (its async exit handlers shut down the subprocesses).
    """
    return asyncio.run(_gather())


def server_summary(tools: list) -> dict[str, list[str]]:
    """Group tool names by the MCP server that provided them, for the sidebar."""
    out: dict[str, list[str]] = {}
    for t in tools:
        # langchain-mcp-adapters prefixes the server name into metadata
        server = getattr(t, "metadata", {}).get("server", "?") if hasattr(t, "metadata") else "?"
        if server == "?":
            # fall back to parsing the tool's name prefix or description
            server = "mcp"
        out.setdefault(server, []).append(t.name)
    return out
