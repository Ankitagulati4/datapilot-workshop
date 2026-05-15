# DataPilot — Student Workshop Map

You're building a **production-feel SQL + Data-Quality chat agent** powered by
[MCP](https://modelcontextprotocol.io). One chat tab, one agent, real tools
served by real MCP servers.

## Architecture (what you ship)

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────┐
│  Streamlit  │ →  │  ChatAgent   │ →  │   MCP servers  │ →  │  SQLite  │
│  (chat UI)  │    │  (LangGraph  │    │ • sqlite-mcp   │    │ shopflow │
│             │    │  ReAct loop) │    │ • datapilot-dq │    │   .db    │
└─────────────┘    └──────────────┘    └────────────────┘    └──────────┘
                          ↑                    ↑
                          │              You build the DQ
                          │              server in Phase 2.
                       Guardrail
                       wraps SQL.
```

## How to build it

Open and follow each MODULE card **in order**.

### Phase 1 — Foundation (90 min)
| # | Card | Time | What you'll build |
|---|---|---|---|
| 00 | [MODULE_00_SETUP.md](MODULE_00_SETUP.md) | 10 | venv, deps, Groq key, `uvx` check |
| 01 | [MODULE_01_MCP.md](MODULE_01_MCP.md) | 15 | `mcp_clients.py` — spawn sqlite-mcp, list 6 tools |
| 02 | [MODULE_02_CHAT.md](MODULE_02_CHAT.md) | 25 | `chat_agent.py` — LangGraph ReAct + memory |
| 03 | [MODULE_03_GUARDRAILS.md](MODULE_03_GUARDRAILS.md) | 15 | `guardrails.py` — block DROP/UPDATE, force LIMIT |
| 04 | [MODULE_04_CHARTS.md](MODULE_04_CHARTS.md) | 10 | `charts.py` — auto line/bar picker |
| 05 | [MODULE_05_CONFIG.md](MODULE_05_CONFIG.md) | 15 | `config/mcp.json` tour — swap to any DB |

### Phase 2 — Platform (90 min)
| # | Card | Time | What you'll build |
|---|---|---|---|
| 06 | [MODULE_06_RECAP.md](MODULE_06_RECAP.md) | 10 | reconnect, smoke test |
| 07 | [MODULE_07_DQ_SERVER.md](MODULE_07_DQ_SERVER.md) | 25 | **your own MCP server** with 4 DQ tools |
| 08 | [MODULE_08_HEALTH.md](MODULE_08_HEALTH.md) | 15 | sidebar health snapshot |
| 09 | [MODULE_09_SAVED.md](MODULE_09_SAVED.md) | 15 | `storage.py` — ★ save & replay |
| 10 | [MODULE_10_COST.md](MODULE_10_COST.md) | 10 | `cost.py` — token + USD badge |
| 11 | [MODULE_11_CLAUDE.md](MODULE_11_CLAUDE.md) | 15 | plug your DQ server into **Claude Desktop** |

## Stuck?

Each MODULE card ends with a **CHECK** section. If yours doesn't pass, copy
`solution/app/<file>.py` over your `student/app/<file>.py` and keep going.

## Files you will write (cumulative)

```
student/
├── app/
│   ├── streamlit_app.py    # grows every module
│   ├── mcp_clients.py      # Module 01
│   ├── chat_agent.py       # Module 02 (+ guardrail in Module 03)
│   ├── guardrails.py       # Module 03
│   ├── charts.py           # Module 04
│   ├── storage.py          # Module 09
│   └── cost.py             # Module 10
├── config/mcp.json         # Module 05
└── mcp_servers/dq_server.py  # Module 07  ← your own MCP server!
```
