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