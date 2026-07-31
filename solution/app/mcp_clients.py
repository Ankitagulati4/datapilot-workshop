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
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path

# Talk MCP with the official SDK directly and keep the sessions alive on ONE
# background event loop. We deliberately AVOID langchain-mcp-adapters'
# MultiServerMCPClient here: its session wrapper deadlocks when several stdio
# servers are driven from one shared event loop and one of them (the RAG server)
# has a slower first call. The raw SDK handles that concurrency cleanly.
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
# The adapter's tool loader operates on a plain ClientSession, so it's fine.
from langchain_mcp_adapters.tools import load_mcp_tools as _load_tools_from_session

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


# --- ONE persistent event loop for the whole app ---------------------------
# MCP stdio servers are subprocesses reached over an asyncio session. We start
# ONE background event loop, open every session ONCE, and keep them alive for
# the app's lifetime -> each later tool call is a fast round-trip (~20 ms) with
# no per-call process spawn and no deadlocks.
_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()
_tools: list | None = None
_cfg: dict | None = None
_error: BaseException | None = None


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Start (once) a background thread running a forever event loop."""
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()
    return _loop


def run_sync(coro):
    """Run a coroutine on the persistent loop and block for its result.

    The chat agent uses this to drive `graph.ainvoke(...)` so the graph AND the
    MCP tool sessions all live on the SAME loop (mixing loops hangs).
    """
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop()).result()


async def _server_main():
    """Open a session per server, publish the tools, then stay alive forever so
    the sessions (and their subprocesses) don't close."""
    global _tools, _cfg, _error
    try:
        servers = _load_config()["mcpServers"]
        async with AsyncExitStack() as stack:
            tools: list = []
            for name, spec in servers.items():
                command = spec["command"]
                # "python" on PATH may not be THIS venv (so deps like chromadb
                # wouldn't be found). Force our own interpreter.
                if command == "python":
                    command = sys.executable
                params = StdioServerParameters(
                    command=command,
                    args=spec.get("args", []),
                    env=spec.get("env"),
                )
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools.extend(await _load_tools_from_session(session))
            _tools, _cfg = tools, servers
            _ready.set()
            await asyncio.Event().wait()   # park forever, keeping sessions open
    except BaseException as e:              # noqa: BLE001 - report boot failures
        _error = e
        _ready.set()


def load_mcp_tools() -> tuple[None, list]:
    """Spawn every MCP server in mcp.json ONCE and return their tools.

    Returns (client, tools). `client` is None -- the sessions live on the
    persistent background loop, so there is no object the caller must hold.
    Idempotent: repeated calls reuse the same live sessions.
    """
    if not _ready.is_set():
        asyncio.run_coroutine_threadsafe(_server_main(), _ensure_loop())
        _ready.wait(timeout=60)
    if _error is not None:
        raise _error
    return None, _tools


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
