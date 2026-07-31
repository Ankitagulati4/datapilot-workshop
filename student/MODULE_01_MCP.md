# Module 01 — Talk to MCP (15 min)

> Goal: spawn an off-the-shelf MCP server (`mcp-server-sqlite`) from Python and list its tools in the sidebar.
https://github.com/modelcontextprotocol/servers

## Why MCP?
MCP = Model Context Protocol. Tools live in **separate processes** with a strict JSON contract. Your agent stops caring whether it's SQLite, Postgres, Snowflake — it just sees `read_query`, `list_tables`, etc.

> ⚠️ **Path note** — we put `mcp.json` **inside** `student/app/config/`
> (sibling of `mcp_clients.py`), matching the layout used by `solution/`.
> That's why `mcp_clients.py` uses `Path(__file__).parent / "config"` below,
> NOT `parents[1]`. Keep these in sync.
>
> The starter `streamlit_app.py` already contains a `sys.path` shim at the
> top so `from app.mcp_clients import ...` works when Streamlit is launched
> from the repo root. Leave it there.

## 1. Create `student/app/config/mcp.json`
```json
{
  "mcpServers": {
    "shopflow-sqlite": {
      "command": "uvx",
      "args": ["--with", "mcp<2", "mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"],
      "transport": "stdio"
    }
  }
}
```

> ⚠️ **Why `--with "mcp<2"`?** `mcp-server-sqlite` calls APIs that were
> removed in the MCP SDK 2.0 (`Server.list_resources`), so on a fresh install
> it crashes at boot with `AttributeError`. Pinning the server to `mcp<2` keeps
> it working. Leave this pin in every `mcp.json` for the rest of the workshop.

## 2. Create `student/app/mcp_clients.py`
MCP stdio servers are subprocesses reached over an asyncio session. Rather than
re-spawn a server (and pay a ~3s process + handshake cost) on every tool call,
we start ONE background event loop, open each session ONCE, and keep them alive
for the app's lifetime. Every later tool call is then a fast round-trip (~20 ms).

```python
# Standard-library helpers
import asyncio     # MCP servers talk over async stdio; we need an event loop
import json        # parse mcp.json
import os          # read environment variables (for ${VAR} substitution)
import sys         # sys.executable -> force servers to use THIS interpreter
import threading   # run ONE long-lived event loop in a background thread
from contextlib import AsyncExitStack  # keep N sessions open together
from pathlib import Path  # cross-platform file paths

# Talk MCP with the official SDK directly (stdio transport + client session).
# We open a persistent ClientSession per server and keep it alive. (We avoid
# langchain-mcp-adapters' MultiServerMCPClient here -- its session wrapper can
# deadlock when several stdio servers share one event loop and one of them, the
# RAG server we build in Module 09, has a slower first call. The raw SDK is fine.)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
# The adapter's tool loader still helps: it wraps each remote MCP tool as a
# LangChain BaseTool. It operates on a plain ClientSession, so it's unaffected.
from langchain_mcp_adapters.tools import load_mcp_tools as _load_tools_from_session

# config/ is a sibling of THIS file (student/app/config/mcp.json).
CONFIG = Path(__file__).parent / "config" / "mcp.json"


def _load_config() -> dict:
    """Read mcp.json and replace every ${VAR} placeholder with the env value."""
    raw = CONFIG.read_text()
    # On Windows the value (e.g. C:\Users\...) contains backslashes; JSON
    # requires them escaped (\\), so we double-up before substituting.
    for k, v in os.environ.items():
        raw = raw.replace(f"${{{k}}}", v.replace("\\", "\\\\"))
    return json.loads(raw)["mcpServers"]


# --- ONE persistent event loop for the whole app ---------------------------
_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()   # set once the sessions are open (or failed)
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
    the sessions (and their subprocesses) don't close. If this task returned,
    the sessions' child tasks would be cancelled and later calls would fail with
    'Connection closed' -- so it parks on an Event that is never set."""
    global _tools, _cfg, _error
    try:
        cfg = _load_config()
        async with AsyncExitStack() as stack:
            tools: list = []
            for name, spec in cfg.items():
                command = spec["command"]
                # "python" on PATH may not be THIS venv (so packages like
                # chromadb wouldn't be found). Force our own interpreter.
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
            _tools, _cfg = tools, cfg
            _ready.set()                 # signal load_mcp_tools() it can return
            await asyncio.Event().wait()  # park forever, keeping sessions open
    except BaseException as e:            # noqa: BLE001 - report boot failures
        _error = e
        _ready.set()


def load_mcp_tools():
    """Spawn every MCP server in mcp.json ONCE and return the discovered tools.

    Returns (tools, cfg). Idempotent: repeated calls reuse the same live
    sessions instead of spawning the servers again.
    """
    if not _ready.is_set():
        asyncio.run_coroutine_threadsafe(_server_main(), _ensure_loop())
        _ready.wait(timeout=60)          # block until sessions are ready
    if _error is not None:
        raise _error
    return _tools, _cfg
```

## 3. Show them in `student/app/streamlit_app.py`
Replace your sidebar block with:
```python
# Pull in the helper we just wrote.
from app.mcp_clients import load_mcp_tools

# Spawn the MCP servers and grab the tools they expose.
# `cfg` is the dict from mcp.json -> useful for showing server names in the UI.
tools, cfg = load_mcp_tools()

with st.sidebar:
    st.header("MCP servers")
    # One green dot per configured server (purely cosmetic confirmation).
    for name in cfg:
        st.success(f"● {name}")
    # Expandable list of every tool the agent CAN call.
    # We show the first 60 chars of each tool's description so the
    # students can see exactly what the LLM will see.
    with st.expander(f"Tools ({len(tools)})"):
        for t in tools:
            st.caption(f"`{t.name}` — {t.description[:60]}")
```

## ✅ CHECK
Reload the app. Sidebar shows:
- ● shopflow-sqlite
- 6 tools listed (`list_tables`, `describe_table`, `read_query`, `write_query`, `create_table`, `append_insight`)

> 💡 We're going to **disallow** `write_query` and `create_table` in Module 03 — but it's fine to see them now.
