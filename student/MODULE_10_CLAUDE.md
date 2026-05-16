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

> ⚠️ **Do NOT use `"command": "python"`.** Claude Desktop launches from
> its own working directory and uses the *system* PATH — not your
> workshop `.venv`. The bare word `python` will resolve to a Python that
> doesn't have `mcp`, `chromadb`, etc. installed, the server will crash
> on import, and Claude will show **`failed — Server disconnected`**.
> Always point `command` at the **absolute path** of your venv's
> `python.exe`.

First, get the exact path of your venv interpreter:
```powershell
& .\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"
```
Copy that path (e.g. `C:\Users\ankit.ANKITA\...\datapilot-workshop\.venv\Scripts\python.exe`)
and use it in the config below.

```json
{
  "mcpServers": {
    "datapilot-dq": {
      "command": "C:\\Users\\YOU\\path\\to\\datapilot-workshop\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\YOU\\path\\to\\datapilot-workshop\\student\\mcp_servers\\dq_server.py",
        "C:\\Users\\YOU\\path\\to\\datapilot-workshop\\data\\shopflow.db"
      ]
    },
    "datapilot-rag": {
      "command": "C:\\Users\\YOU\\path\\to\\datapilot-workshop\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\YOU\\path\\to\\datapilot-workshop\\student\\mcp_servers\\rag_server.py"
      ]
    }
  }
}
```

A copy-paste template lives at `claude_desktop_config.example.json` in
the repo root.

> ⚠️ **Use absolute paths** everywhere with double-backslashes (`\\`)
> or forward slashes (`/`). JSON treats `\` as an escape character — a
> single backslash is a syntax error.

> ✅ **Verify the venv is wired correctly** before restarting Claude:
> ```powershell
> & "C:\Users\YOU\path\to\datapilot-workshop\.venv\Scripts\python.exe" -c "import mcp, chromadb; print('ok')"
> ```
> If that prints `ok`, Claude Desktop will spawn the servers successfully.
> If it errors with `ModuleNotFoundError`, run
> `pip install -r requirements.txt` *inside the venv* first.

## 4. Quit & re-open Claude Desktop
Fully quit (system tray icon → Quit). Re-launch. Click the 🛠️ tools icon
in the chat composer.

You should see **two** servers listed:
- `datapilot-dq` · 4 tools
- `datapilot-rag` · 2 tools

### Troubleshooting — `failed — Server disconnected`
This is the most common error. Click **View Logs** to confirm. Almost
always one of:

| Symptom in logs | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'mcp'` or `'chromadb'` | `command` is `"python"` instead of your venv's `python.exe` | See section 3 — use the absolute venv path |
| `FileNotFoundError: [...] dq_server.py` | Relative path in `args` | Use absolute paths everywhere |
| `Invalid \\escape` JSON parse error | Single backslash in a Windows path | Double them (`\\`) or use forward slashes (`/`) |
| `sqlite3.OperationalError: unable to open database file` | DB path wrong / file missing | Run `python data/build_shopflow.py` first |
| `Collection [shopflow_docs] does not exist` | RAG index never built | Run `python student/mcp_servers/build_rag_index.py` first |

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
