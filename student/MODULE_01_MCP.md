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
import asyncio, json, os
from pathlib import Path
from langchain_mcp_adapters.client import MultiServerMCPClient

# config/ is a sibling of this file (student/app/config/mcp.json)
CONFIG = Path(__file__).parent / "config" / "mcp.json"

def _load_config() -> dict:
    raw = CONFIG.read_text()
    # expand ${VAR} from environment
    for k, v in os.environ.items():
        raw = raw.replace(f"${{{k}}}", v.replace("\\", "\\\\"))
    return json.loads(raw)["mcpServers"]

def load_mcp_tools():
    cfg = _load_config()
    client = MultiServerMCPClient(cfg)
    tools = asyncio.run(client.get_tools())
    return tools, cfg
```

## 3. Show them in `student/app/streamlit_app.py`
Replace your sidebar block with:
```python
from app.mcp_clients import load_mcp_tools

tools, cfg = load_mcp_tools()

with st.sidebar:
    st.header("MCP servers")
    for name in cfg:
        st.success(f"● {name}")
    with st.expander(f"Tools ({len(tools)})"):
        for t in tools:
            st.caption(f"`{t.name}` — {t.description[:60]}")
```

## ✅ CHECK
Reload the app. Sidebar shows:
- ● shopflow-sqlite
- 6 tools listed (`list_tables`, `describe_table`, `read_query`, `write_query`, `create_table`, `append_insight`)

> 💡 We're going to **disallow** `write_query` and `create_table` in Module 03 — but it's fine to see them now.
