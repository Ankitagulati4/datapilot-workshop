# Module 10 — Plug BOTH MCP servers into Claude Desktop 🎉 (15 min)

> Goal: open Claude Desktop, ask one question, and watch Claude call
> **your** `dq_server.py` **and** `rag_server.py` in a single turn. That
> is the entire MCP payoff in one screenshot.

## 1. Install Claude Desktop (free)
https://claude.ai/download

## 2. Locate the config
Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Open it in VS Code:
```powershell
code $env:APPDATA\Claude\claude_desktop_config.json
```
(If the file doesn't exist, create it — Claude Desktop will read it on
next launch.)

## 3. Paste this — adjust paths!

```json
{
  "mcpServers": {
    "datapilot-dq": {
      "command": "python",
      "args": [
        "C:\\Users\\YOU\\path\\to\\session7-sql-data-agent\\student\\mcp_servers\\dq_server.py",
        "C:\\Users\\YOU\\path\\to\\session7-sql-data-agent\\data\\shopflow.db"
      ]
    },
    "datapilot-rag": {
      "command": "python",
      "args": [
        "C:\\Users\\YOU\\path\\to\\session7-sql-data-agent\\student\\mcp_servers\\rag_server.py"
      ]
    }
  }
}
```

A copy-paste template lives at `claude_desktop_config.example.json` in
the repo root.

> ⚠️ **Use absolute paths** with double-backslashes (`\\`) or forward
> slashes (`/`) — Claude Desktop runs the command from its own cwd.

> ⚠️ **Use the same `python.exe` your venv uses.** The simplest way:
> ```powershell
> Get-Command python | Select-Object -ExpandProperty Source
> ```
> Use that path as `"command"` instead of just `"python"` if Claude
> can't find your venv on PATH.

## 4. Quit & re-open Claude Desktop
Fully quit (system tray icon → Quit). Re-launch. Click the 🛠️ tools icon
in the chat composer.

You should see **two** servers listed:
- `datapilot-dq` · 4 tools
- `datapilot-rag` · 2 tools

## 5. The combined demo

Ask Claude this single question:

> "Using my MCP servers — first tell me how fresh the orders table is,
> then look up what our returns policy says about refund processing times."

Claude will:
1. Call `datapilot-dq.check_freshness("orders")` → e.g. `[STALE] orders.order_date: latest 2026-04-30 (283 h ago)`
2. Call `datapilot-rag.search_docs("returns policy refund processing")` → the returns-policy doc
3. Compose a single answer using both results

**Two of your servers. One Claude turn. Zero new code on Claude's side.**

## ✅ CHECK

You just shipped two tools that **any MCP-aware app** can use, regardless
of who wrote it:

- ✅ Your Streamlit app (built across modules 01–09)
- ✅ Claude Desktop (this module)
- ✅ Cursor, Continue.dev, Zed, etc. (same config file format)

That's the power of MCP. 🎯

## Bonus

- Add a 3rd tool to `dq_server.py`: `top_categories(n=5)` — reuse the
  agent's category-revenue SQL inside the tool. Restart Claude. Ask
  *"what are the top 5 categories"* and watch Claude call it.
- Add more documents to `docs/` (e.g. a brand-voice guide). Rebuild the
  index. Restart Claude. Ask Claude something only your new doc knows.
- Ship a PR to your team's data-quality MCP server. (Now you can.)

## Talking points

- **You went from MCP *consumer* to MCP *publisher*** in 9 modules.
- **The same servers** run unchanged in 3 different agents (DataPilot,
  Claude Desktop, anything else you bolt on).
- **The boundary between "infrastructure" and "AI app" moved**. Anything
  worth doing programmatically now becomes a tool every AI client can
  use, with zero per-client integration work.

## Where this leads (separate sessions)

- Cost telemetry & rate-limit handling for production
- Production deployment (Docker, secrets, transport over HTTP/SSE)
- Retrieval quality (chunking, hybrid search, eval)
- Multi-tenant MCP servers behind an auth boundary
