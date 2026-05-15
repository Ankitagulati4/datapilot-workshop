# Module 11 — Plug your MCP server into Claude Desktop 🎉 (15 min)

> Goal: open Claude Desktop, type "is the orders data fresh?", and Claude calls **your** `dq_server.py`. Wow moment.

## 1. Install Claude Desktop (free)
https://claude.ai/download

## 2. Locate the config
Windows: `%APPDATA%\Claude\claude_desktop_config.json`
(Open in VS Code: `code $env:APPDATA\Claude\claude_desktop_config.json`)

## 3. Paste this (adjust paths!)
```json
{
  "mcpServers": {
    "datapilot-dq": {
      "command": "python",
      "args": [
        "C:\\Users\\YOU\\path\\to\\session7-sql-data-agent\\student\\mcp_servers\\dq_server.py",
        "C:\\Users\\YOU\\path\\to\\session7-sql-data-agent\\data\\shopflow.db"
      ]
    }
  }
}
```
A copy-paste template lives at `claude_desktop_config.example.json`.

## 4. Quit & re-open Claude Desktop
- Click the 🛠️ (tools) icon in the chat box.
- You should see **datapilot-dq** with 4 tools.

## 5. Ask Claude
> "Use the datapilot-dq tools — how fresh is the orders table and how many duplicates are in customer.email?"

Claude calls `check_freshness("orders")` and `check_duplicates("customers","email")` and answers.

## ✅ CHECK
You just shipped a tool that **any MCP-aware app** can use:
- ✅ Your Streamlit app (built across 11 PARTs)
- ✅ Claude Desktop
- ✅ Cursor, Continue.dev, Zed, etc.

That's the power of MCP. 🎯

## Bonus
- Add a 5th tool: `top_categories(table, n=5)`.
- Wire the tool into both your app **and** Claude Desktop.
- Ship a PR to your team's data-quality MCP server. (Now you can.)
