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

## Adding a 2nd server — try an existing one

`mcp.json` can register any number of servers. To see this in action, add
an off-the-shelf MCP server that already exists on PyPI (no code to write).
For example, the official **fetch** server gives the agent a `fetch` tool
that can pull a URL:

```json
{
  "mcpServers": {
    "shopflow-sqlite": { "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"], "transport": "stdio" },
    "web-fetch":       { "command": "uvx", "args": ["mcp-server-fetch"], "transport": "stdio" }
  }
}
```

Restart the app → sidebar now shows **two ● badges** and the tools list
grows by one (`fetch`). Remove the entry afterwards to keep the demo focused.

> 💡 The point isn't *which* server you add — it's that `mcp.json` is the
> single place where capabilities plug in. The agent, the guardrail, and
> the charts code don't change.

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
- You added a 2nd entry (e.g. `mcp-server-fetch`), restarted, and saw 2 ● badges.
- You removed the 2nd entry to keep the workshop scope clean.
