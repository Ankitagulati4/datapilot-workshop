# Module 07 — Build your own MCP server (25 min) ⭐

> Goal: a Python file that exposes 4 data-quality tools over MCP. Same protocol Anthropic, Cursor, and Continue.dev all speak.

## 1. Install FastMCP
Already in `requirements.txt` (`mcp>=1.0`). Confirm:
```powershell
python -c "from mcp.server.fastmcp import FastMCP; print('ok')"
```

## 2. Create `student/mcp_servers/dq_server.py`
```python
"""DataPilot DQ — a tiny MCP server with 4 quality-check tools.

Run standalone:  python student/mcp_servers/dq_server.py data/shopflow.db
Used by:         the chat agent (auto-spawned via student/app/config/mcp.json)
"""
import sys, sqlite3
from datetime import datetime, timezone
# FastMCP turns ordinary Python functions into MCP tools via a decorator.
# It handles the JSON-RPC framing, stdio transport, schema generation, etc.
from mcp.server.fastmcp import FastMCP

# CLI arg 1 = path to the SQLite DB. Falls back to the workshop default.
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/shopflow.db"

# `FastMCP(name)` creates the server. The name is what the client (our agent
# or Claude Desktop) will see in its sidebar.
mcp = FastMCP("datapilot-dq")

def _conn():
    """Open a fresh SQLite connection per tool call (cheap + thread-safe)."""
    return sqlite3.connect(DB_PATH)

def _detect_ts_column(c, table):
    """Guess the timestamp column for `table`. Picks the first column whose
    name contains 'date', '_at', 'time', or 'timestamp'."""
    cols = c.execute(f"PRAGMA table_info({table})").fetchall()
    cands = [n for _, n, *_ in cols if any(k in n.lower() for k in ("date","_at","time","timestamp"))]
    return cands[0] if cands else None

# --- TOOLS ------------------------------------------------------------------
# Every @mcp.tool() decorator publishes one tool to MCP clients. The function's
# DOCSTRING is what the LLM reads when deciding whether to call this tool.
# Write docstrings like you're writing UX microcopy -- they ARE the API.

@mcp.tool()
def count_rows(table: str) -> str:
    """Total row count for a table."""
    with _conn() as c:
        n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return f"{table}: {n} rows"

@mcp.tool()
def check_freshness(table: str, ts_column: str | None = None) -> str:
    """Age of newest row, in hours. Auto-detects timestamp column if not given."""
    with _conn() as c:
        # Use the explicit column the caller passed, or auto-detect one.
        col = ts_column or _detect_ts_column(c, table)
        if not col: return f"{table}: no timestamp column"
        v = c.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
    if not v: return f"{table}: empty"
    try:
        # SQLite stores datetimes as ISO strings. "Z" -> "+00:00" so fromisoformat works.
        latest = datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except ValueError:
        return f"{table}.{col}: {v}"
    # If the stored value is naive, assume UTC so the subtraction below is valid.
    if latest.tzinfo is None: latest = latest.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - latest).total_seconds()/3600
    # Badge encodes the SLA -- fresh < 24h, stale otherwise.
    badge = "OK" if age < 24 else "STALE"
    return f"[{badge}] {table}.{col}: latest {latest.date()} ({age:.1f}h ago)"

@mcp.tool()
def check_nulls(table: str, column: str) -> str:
    """% of NULLs in a column."""
    with _conn() as c:
        # One round-trip: total row count + null count via conditional sum.
        total, n = c.execute(f"SELECT COUNT(*), SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) FROM {table}").fetchone()
    if not total: return f"{table}.{column}: empty"
    pct = (n or 0) * 100 / total
    return f"{table}.{column}: {n}/{total} NULL ({pct:.1f}%)"

@mcp.tool()
def check_duplicates(table: str, column: str) -> str:
    """How many duplicate values in a column."""
    with _conn() as c:
        # COUNT(*) - COUNT(DISTINCT col) = number of "extra" rows beyond uniques.
        dups = c.execute(
            f"SELECT COUNT(*) - COUNT(DISTINCT {column}) FROM {table}").fetchone()[0]
    return f"{table}.{column}: {dups} duplicates"

if __name__ == "__main__":
    # transport="stdio" = the standard MCP transport: JSON-RPC over stdin/stdout.
    # The parent process (our chat agent / Claude Desktop) forks us and pipes
    # requests in via stdin; we reply on stdout. Stderr is free for logging.
    mcp.run(transport="stdio")
```

## 3. Smoke-test the server **standalone**

### 3a. Just boot it
```powershell
python student/mcp_servers/dq_server.py data/shopflow.db
```
It should sit silently on stdin (waiting for JSON-RPC). That silence IS the
success signal — the server has bound its stdio transport and is parked
waiting for a client. Press Ctrl+C to exit.

> Why so quiet? MCP servers speak JSON-RPC over **stdout**. If the server
> printed banners or logs to stdout it would corrupt the protocol stream.
> All human-readable logs MUST go to stderr.

### 3b. Poke it with the MCP Inspector (browser UI, zero code)
Anthropic ships an official debugger called **MCP Inspector**. It launches
your server, speaks the protocol for you, and gives you a clickable
browser UI to list and call tools. Perfect for sanity-checking before you
plug into the agent.

You need Node.js installed (`node --version` → v18+). Then from the repo
root:

```powershell
npx @modelcontextprotocol/inspector
```

First run will download the inspector (~10s). It then prints something like:

```
🔍 MCP Inspector is up and running at:
   http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=abc123def456...
```

> ⚠️ **Open the FULL URL** including `?MCP_PROXY_AUTH_TOKEN=...`. Since
> v0.14 the inspector requires this session token. Visiting plain
> `http://localhost:6274` shows *"Error Connecting to MCP Inspector
> Proxy"* — that error is about the inspector itself, not your server.
>
> Or disable auth (localhost only, never in prod):
> ```powershell
> $env:DANGEROUSLY_OMIT_AUTH = "true"
> npx @modelcontextprotocol/inspector
> ```

#### Fill the left-hand form
The fields default to placeholder text — **overwrite them** with:

| Field          | Value                                                   |
|----------------|---------------------------------------------------------|
| Transport Type | `STDIO`                                                 |
| Command        | `python`                                                |
| Arguments      | `student/mcp_servers/dq_server.py data/shopflow.db`     |

The Arguments field takes a single string; the inspector splits it on
spaces. So you literally type:

```
student/mcp_servers/dq_server.py data/shopflow.db
```

Click **Connect**. The red dot turns green.

#### Try the tools
1. Click **Tools** in the top nav → **List Tools**. You should see all 4:
   `count_rows`, `check_freshness`, `check_nulls`, `check_duplicates`.
2. Click `count_rows`, set `table = orders`, **Run Tool** → `orders: 4000 rows`.
3. `check_freshness` with `table = orders` → `[OK] orders.order_date: ...`.
4. `check_nulls` with `table = customers`, `column = email`.
5. `check_duplicates` with `table = customers`, `column = email`.

If all 4 return sensible strings, the server is healthy in isolation.
Press Ctrl+C in the terminal to stop the inspector.

> Why this beats writing a probe script: the inspector is the *same* thing
> Claude Desktop / Cursor / our LangChain agent do — JSON-RPC over stdio —
> just with a UI on top. What you see in the Inspector is exactly what the
> LLM will see when it lists tools later.

> **No Node installed?** Skip this step — `python student/mcp_servers/dq_server.py data/shopflow.db`
> staying silent (3a) is already enough proof the server boots. You'll
> exercise the tools through the agent in Section 6.

✅ Server is healthy in isolation. **Now** we wire it into the agent.

## 4. Register it in `student/app/config/mcp.json`
Add a 2nd entry (keep the existing `shopflow-sqlite` block):
```json
{
  "mcpServers": {
    "shopflow-sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"],
      "transport": "stdio"
    },
    "datapilot-dq": {
      "command": "python",
      "args": ["student/mcp_servers/dq_server.py", "${SHOPFLOW_DB}"],
      "transport": "stdio"
    }
  }
}
```

## 5. Open the allow-list in `student/app/chat_agent.py`
Back in Module 03 we added a `SAFE` set so the LLM can only see whitelisted
tools. The 4 new DQ tools are NOT in that set yet — so even though the
server is running, the agent will silently filter them out (sidebar stays at
3 tools, and "is the data fresh?" gets answered with `SELECT MAX(...)`
instead of `check_freshness`).

Find this line:
```python
SAFE = {"read_query", "list_tables", "describe_table"}
```

Replace with:
```python
SAFE = {
    # shopflow-sqlite
    "read_query", "list_tables", "describe_table",
    # datapilot-dq (Module 07)
    "count_rows", "check_freshness", "check_nulls", "check_duplicates",
}
```

> Why an allow-list at all? Defence in depth. The MCP server *could* one day
> expose a destructive tool; the agent should never even *see* it unless we
> explicitly opt in. New tool → one-line review → add to `SAFE`.

## ✅ CHECK — Sidebar
Stop Streamlit (Ctrl+C) and restart it (the `@st.cache_resource` bootstrap
only re-runs on a fresh process). Sidebar should show:
- Two ● badges: `shopflow-sqlite`, `datapilot-dq`
- **Tools (7)** — the 3 SQL tools + the 4 new DQ tools

## 6. End-to-end storytelling — exercise all 4 DQ tools through the agent

This is the payoff. We built a server, probed it raw, registered it, and
allow-listed its tools. Now let's tell a story an analyst would actually
tell, and watch the agent pick the *right tool for each question* —
sometimes one of ours, sometimes the SQL tool, sometimes **both in one
turn**.

Ask these prompts in order in the chat. After each, open the **steps**
expander and verify the tool calls match what's predicted.

### Story 1 — "Can I trust today's dashboard?"
> **You:** *Is the orders data fresh enough to report on today?*

Expected trace:
- `check_freshness({'table': 'orders'})` → `[OK]` or `[STALE]` badge

Why it matters: the agent now reaches for a *purpose-built* DQ tool instead
of writing `SELECT MAX(order_date)` and eyeballing the date.

### Story 2 — "How big is each table?"
> **You:** *How many rows are in customers, products, and orders?*

Expected trace: **3 calls** to `count_rows`, one per table.

This shows the agent fanning out a single user question into multiple tool
calls — the ReAct loop in action.

### Story 3 — "Is our customer data clean?"
> **You:** *Check the customers table for null emails and duplicate emails.*

Expected trace:
- `check_nulls({'table': 'customers', 'column': 'email'})`
- `check_duplicates({'table': 'customers', 'column': 'email'})`

Two DQ tools called back-to-back in one turn. The agent decomposed
"clean?" into two concrete checks.

### Story 4 — Cross-server combo (the money shot 💰)
> **You:** *First confirm orders is fresh, then show me total revenue from completed orders in the last 7 days.*

Expected trace mixes BOTH servers:
- `check_freshness({'table': 'orders'})`   ← from `datapilot-dq`
- `list_tables({})` / `describe_table({'table_name': 'orders'})`  ← schema discovery
- `read_query({'query': 'SELECT SUM(total_amount) ... WHERE status = \'completed\' AND order_date >= DATE(\'now\', \'-7 days\')'})`  ← from `shopflow-sqlite`

This is the whole point of MCP: **the agent doesn't know or care that
`check_freshness` and `read_query` come from two different processes**. To
the LLM they're just tools on the same menu. We composed two independent
servers into one analyst workflow without changing a line of agent code.

### Story 5 — Let the agent diagnose
> **You:** *Run a quick data quality health check on the orders table — freshness, row count, and any null customer_ids.*

Expected trace: **3 calls in one turn** — `check_freshness`, `count_rows`,
`check_nulls(orders, customer_id)` — followed by a 2-sentence summary.

You've just built a one-prompt DQ dashboard.

### Troubleshooting
- Sidebar still says **Tools (3)** → you forgot step 5, or Streamlit is
  using a cached agent. Fully stop the process and `streamlit run ...`
  again.
- Only `shopflow-sqlite` badge appears → check `mcp.json` is valid JSON
  (trailing commas break it) and that `python student/mcp_servers/dq_server.py data/shopflow.db`
  runs standalone without errors.
- Agent answers freshness with `SELECT MAX(order_date)` instead of calling
  `check_freshness` → the DQ tools are registered but not in `SAFE`.
  Re-check step 5.
- Agent calls ONE tool when you expected two → re-phrase with the word
  "and" or "both" (e.g. *"check nulls **and** duplicates on email"*). The
  ReAct loop will plan multiple steps when the prompt clearly asks for
  multiple things.
