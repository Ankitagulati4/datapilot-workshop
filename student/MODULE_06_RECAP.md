# Module 06 — Recap & reconnect (10 min)

> Goal: prove yesterday's app still runs, then warm up for the DQ server build.

## 1. Re-launch
```powershell
.\.venv\Scripts\Activate.ps1
.\run.ps1
```

## 2. Smoke checklist
Ask each question and verify the answer.
| # | Question | Expected |
|---|---|---|
| 1 | how many customers? | 800 |
| 2 | top 5 categories by revenue | bar chart |
| 3 | orders per month in 2025 | line chart |
| 4 | drop table customers | refused / GUARDRAIL BLOCK |

## 3. Re-read what we built

```
student/app/
  ├ streamlit_app.py   # UI + chart hook
  ├ mcp_clients.py     # spawns MCP servers
  ├ chat_agent.py      # LangGraph ReAct + memory + guarded read_query
  ├ guardrails.py      # SQL allow-list + LIMIT injection
  ├ llm.py             # ChatGroq
  └ charts.py          # auto line/bar
student/app/config/mcp.json # 1 server today, 2 by end of Module 07
```

## Today's plan (90 min)

| Part | Deliverable |
|---|---|
| **SUN 1** | Build YOUR OWN MCP server — `dq_server.py` with 4 DQ tools |
| SUN 2 | Sidebar "Health snapshot" calling those tools |
| SUN 3 | Build a SECOND MCP server — `rag_server.py` with semantic search over docs |
| SUN 4 | Plug BOTH custom servers into **Claude Desktop** 🎉 |

> 🎯 The big idea today: yesterday you *consumed* MCP. Today you *publish* MCP — twice, in two completely different shapes (SQL DQ + semantic search).
