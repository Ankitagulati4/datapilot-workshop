# Checkpoints

If you fall behind in any PART, **the canonical "after this part" code lives in
`solution/`**. We don't ship per-part snapshots because they'd drift; instead
each PART card lists exactly which files to copy.

## Recovery cheatsheet

| If you got stuck during… | Copy these files from `solution/app/` over `student/app/` |
|---|---|
| Module 01 (MCP) | `mcp_clients.py` and `solution/app/config/mcp.json` (path adjusted) |
| Module 02 (Chat) | `chat_agent.py`, `llm.py` |
| Module 03 (Guardrails) | `guardrails.py` (and re-do the wrap step in `chat_agent.py`) |
| Module 04 (Charts) | `charts.py` |
| Module 05 (Config) | nothing to copy — pure walkthrough |
| Module 07 (DQ server) | `solution/mcp_servers/dq_server.py` |
| Module 08 (Health) | sidebar block from `solution/app/streamlit_app.py` |
| Module 09 (RAG server) | `solution/mcp_servers/rag_server.py` + `build_rag_index.py` |
| Module 10 (Claude) | use `claude_desktop_config.example.json` |

## "Just run the finished thing"
```powershell
$env:DATAPILOT_APP = "solution"
.\run.ps1
```
This launches `solution/app/streamlit_app.py` — a fully working reference.
Reset:
```powershell
$env:DATAPILOT_APP = "student"
.\run.ps1
```
