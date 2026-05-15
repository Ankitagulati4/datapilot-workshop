"""DataPilot DQ MCP Server.

A small MCP server that exposes 4 production-style data-quality tools
to ANY MCP client (our chat agent, Claude Desktop, Cursor, etc.).

This is the "build your own MCP server" lesson in Module 07. About
50 lines of FastMCP. Same toolkit can be reused across many products.

Run standalone:
    python solution/mcp_servers/dq_server.py data/shopflow.db
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_REPO_ROOT = Path(__file__).resolve().parents[2]
_arg = sys.argv[1] if len(sys.argv) > 1 else "data/shopflow.db"
DB_PATH = Path(_arg) if Path(_arg).is_absolute() else (_REPO_ROOT / _arg)
if not DB_PATH.exists():
    raise FileNotFoundError(
        f"DB not found: {DB_PATH}. Run: python data/build_shopflow.py")

mcp = FastMCP("datapilot-dq")


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _detect_ts_column(c: sqlite3.Connection, table: str) -> str | None:
    """Pick the most likely timestamp column for `table`."""
    cols = c.execute(f"PRAGMA table_info({table})").fetchall()
    candidates = [name for _, name, *_ in cols
                  if any(k in name.lower() for k in ("date", "_at", "time", "timestamp"))]
    return candidates[0] if candidates else None


@mcp.tool()
def check_freshness(table: str, ts_column: str | None = None) -> str:
    """How fresh is `table`? Returns the age of the most recent row in hours.

    If `ts_column` is omitted, picks a timestamp-looking column automatically
    (anything containing 'date', '_at', 'time', or 'timestamp').
    Use this when the user asks 'is the data current?' or 'are orders fresh?'.
    """
    with _conn() as c:
        col = ts_column or _detect_ts_column(c, table)
        if not col:
            return f"{table}: no timestamp column found. Pass ts_column=..."
        row = c.execute(f"SELECT MAX({col}) FROM {table}").fetchone()
    if not row or row[0] is None:
        return f"{table}: no rows in {col}."
    raw = str(row[0])
    try:
        latest = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return f"{table}.{col} latest value: {raw} (not a parseable timestamp)"
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age_h = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
    badge = "OK" if age_h < 24 else "STALE"
    return f"[{badge}] {table}.{col}: latest {latest.date()} ({age_h:.1f} h ago)"


@mcp.tool()
def check_nulls(table: str, column: str) -> str:
    """Count NULL values in `column` of `table`.

    Use this for 'are there missing values in customer emails?' style questions.
    """
    with _conn() as c:
        n_null = c.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
        ).fetchone()[0]
        n_total = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    pct = (n_null / n_total * 100) if n_total else 0
    badge = "OK" if pct < 1 else ("WARN" if pct < 5 else "FAIL")
    return f"[{badge}] {table}.{column}: {n_null}/{n_total} NULL ({pct:.2f}%)"


@mcp.tool()
def check_duplicates(table: str, key_columns: str) -> str:
    """Count duplicate keys. `key_columns` is a comma-separated list, e.g. 'order_id'.

    Use this for 'are there duplicate orders?' style questions.
    """
    keys = [k.strip() for k in key_columns.split(",") if k.strip()]
    keys_sql = ", ".join(keys)
    with _conn() as c:
        dup = c.execute(
            f"SELECT COUNT(*) FROM (SELECT {keys_sql} FROM {table} "
            f"GROUP BY {keys_sql} HAVING COUNT(*) > 1)"
        ).fetchone()[0]
    badge = "OK" if dup == 0 else "FAIL"
    return f"[{badge}] {table}({keys_sql}): {dup} duplicate key(s)"


@mcp.tool()
def count_rows(table: str) -> str:
    """Return the row count of `table`. Quick health-check tool."""
    with _conn() as c:
        n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return f"{table}: {n} rows"


if __name__ == "__main__":
    mcp.run()
