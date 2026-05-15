# Module 01 — Talk to MCP (15 min)

> Goal: spawn an off-the-shelf MCP server (`mcp-server-sqlite`) from Python and list its tools in the sidebar.

## Why MCP?
MCP = Model Context Protocol. Tools live in **separate processes** with a
strict JSON contract. Your agent stops caring whether it's SQLite, Postgres,
Snowflake — it just sees `read_query`, `list_tables`, etc.

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
      "args": ["mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"],
      "transport": "stdio"
    }
  }
}
```

## 2. Create `student/app/mcp_clients.py`
```python
# Standard-library helpers
import asyncio   # MCP servers talk over async stdio; we need an event loop
import json      # parse mcp.json
import os        # read environment variables (for ${VAR} substitution)
from pathlib import Path  # cross-platform file paths

# `langchain-mcp-adapters` is the glue: it speaks MCP to N servers and
# returns each remote tool wrapped as a LangChain BaseTool the agent can call.
from langchain_mcp_adapters.client import MultiServerMCPClient

# config/ is a sibling of THIS file (student/app/config/mcp.json).
# Using __file__ makes the path correct no matter where Streamlit is launched from.
CONFIG = Path(__file__).parent / "config" / "mcp.json"


def _load_config() -> dict:
    """Read mcp.json and replace every ${VAR} placeholder with the env value."""
    raw = CONFIG.read_text()
    # expand ${VAR} from environment.
    # On Windows the value (e.g. C:\Users\...) contains backslashes;
    # JSON requires them escaped (\\), so we double-up before substituting.
    for k, v in os.environ.items():
        raw = raw.replace(f"${{{k}}}", v.replace("\\", "\\\\"))
    # Parse the substituted text and return only the servers dict.
    return json.loads(raw)["mcpServers"]


def load_mcp_tools():
    """Spawn every MCP server in mcp.json and return the discovered tools."""
    cfg = _load_config()
    # MultiServerMCPClient forks each server as a subprocess, opens stdio
    # pipes, does the MCP handshake, and asks each server for its tool list.
    client = MultiServerMCPClient(cfg)
    # `get_tools()` is async (it awaits handshakes); asyncio.run drives it
    # from our synchronous Streamlit thread.
    tools = asyncio.run(client.get_tools())
    return tools, cfg
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
