# Module 05 — Config tour: swap the database (15 min)

> Goal: understand `mcp.json` so well that swapping SQLite → Postgres takes 4 lines.

## Read your current `student/app/config/mcp.json`

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

## What each field means
- **`command`** — executable to launch (`uvx` runs published Python MCP servers without polluting your env).
- **`args`** — CLI args. `${SHOPFLOW_DB}` is expanded from your `.env`.
- **`transport`** — `stdio` (over pipes) is the simplest. The server prints JSON-RPC on stdout.

## Adding a 2nd server (preview Module 07)
```json
{
  "mcpServers": {
    "shopflow-sqlite": { "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"], "transport": "stdio" },
    "datapilot-dq":   { "command": "python", "args": ["student/mcp_servers/dq_server.py", "${SHOPFLOW_DB}"], "transport": "stdio" }
  }
}
```
Restart the app → sidebar now shows both servers.

## Swapping to Postgres (would-be 4-line diff)
```json
"shopflow-pg": {
  "command": "uvx",
  "args": ["mcp-server-postgres", "${PG_URL}"],
  "transport": "stdio"
}
```
That's it. The agent code, the guardrail, the charts — none of it changes.
**This is the MCP payoff.**

## ✅ CHECK
- You can describe each field of `mcp.json` to your neighbour.
- You added a 2nd entry, restarted, and saw 2 ● badges.
- You removed the 2nd entry (we'll properly add it in Module 07).
