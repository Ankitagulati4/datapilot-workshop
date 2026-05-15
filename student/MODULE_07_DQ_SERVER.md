# Module 07 — Build your own MCP server (25 min) ⭐

> Goal: a Python file that exposes 4 data-quality tools over MCP. Same protocol Anthropic, Cursor, and Continue.dev all speak.

## 1. Install FastMCP
Already in `requirements.txt` (`mcp>=1.0`). Confirm:
```powershell
python -c "from mcp.server.fastmcp import FastMCP; print('ok')"
```

## 2. Create `student/mcp_servers/dq_server.py`
```python
"""DataPilot DQ — a tiny MCP server with 4 quality-check tools."""
import sys, sqlite3
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "data/shopflow.db"
mcp = FastMCP("datapilot-dq")

def _conn(): return sqlite3.connect(DB_PATH)

def _detect_ts_column(c, table):
    cols = c.execute(f"PRAGMA table_info({table})").fetchall()
    cands = [n for _, n, *_ in cols if any(k in n.lower() for k in ("date","_at","time","timestamp"))]
    return cands[0] if cands else None

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
        col = ts_column or _detect_ts_column(c, table)
        if not col: return f"{table}: no timestamp column"
        v = c.execute(f"SELECT MAX({col}) FROM {table}").fetchone()[0]
    if not v: return f"{table}: empty"
    try:
        latest = datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except ValueError:
        return f"{table}.{col}: {v}"
    if latest.tzinfo is None: latest = latest.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - latest).total_seconds()/3600
    badge = "OK" if age < 24 else "STALE"
    return f"[{badge}] {table}.{col}: latest {latest.date()} ({age:.1f}h ago)"

@mcp.tool()
def check_nulls(table: str, column: str) -> str:
    """% of NULLs in a column."""
    with _conn() as c:
        total, n = c.execute(f"SELECT COUNT(*), SUM(CASE WHEN {column} IS NULL THEN 1 ELSE 0 END) FROM {table}").fetchone()
    if not total: return f"{table}.{column}: empty"
    pct = (n or 0) * 100 / total
    return f"{table}.{column}: {n}/{total} NULL ({pct:.1f}%)"

@mcp.tool()
def check_duplicates(table: str, column: str) -> str:
    """How many duplicate values in a column."""
    with _conn() as c:
        dups = c.execute(
            f"SELECT COUNT(*) - COUNT(DISTINCT {column}) FROM {table}").fetchone()[0]
    return f"{table}.{column}: {dups} duplicates"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

## 3. Smoke-test the server **standalone**
```powershell
python student/mcp_servers/dq_server.py data/shopflow.db
```
It should sit silently on stdin (waiting for JSON-RPC). Press Ctrl+C.

## 4. Register it in `student/app/config/mcp.json`
Add a 2nd entry:
```json
"datapilot-dq": {
  "command": "python",
  "args": ["student/mcp_servers/dq_server.py", "${SHOPFLOW_DB}"],
  "transport": "stdio"
}
```

## ✅ CHECK
Restart the app. Sidebar:
- Two ● badges: `shopflow-sqlite`, `datapilot-dq`
- Tools count jumps from 3 to 7 (4 new DQ tools added — the whitelist auto-allows them; if not, add to `SAFE` set in `chat_agent.py`)

Then ask: **"is the orders data fresh?"** → agent calls `check_freshness("orders")` and replies with the badge + age.
