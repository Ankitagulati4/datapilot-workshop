# DataPilot — an MCP-native SQL & Data-Quality agent

> A production-shaped reference project: **one chat tab, one ReAct agent,
> three real MCP servers, ~700 lines of Python**. Built live with the audience
> across **two 90-minute sessions** (~3 hours of seat time).

---

## Table of contents
1. [What you'll build](#1-what-youll-build)
2. [Tech stack — every piece, and why](#2-tech-stack--every-piece-and-why)
3. [Core concepts (start here if you're new)](#3-core-concepts-start-here-if-youre-new)
4. [Architecture](#4-architecture)
5. [The data: ShopFlow](#5-the-data-shopflow)
6. [Repository layout](#6-repository-layout)
7. [Quick start](#7-quick-start)
8. [The webinar script — 11 modules, each visible in the UI](#8-the-webinar-script--11-modules-each-visible-in-the-ui)
9. [Validation](#9-validation)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. What you'll build

A Streamlit app where a non-technical user types business questions like
*"top 5 product categories by revenue"* and gets back a one-line answer, a
sortable table, and a Plotly chart. The sidebar shows red/green
data-quality badges and the list of connected MCP servers. The agent also
answers conceptual questions like *"what does VIP mean?"* by searching
your `docs/*.md` corpus through a second in-house MCP server.

Under the hood, a **LangGraph ReAct agent** decides which tool to call.
The tools live in **three MCP servers** running as separate subprocesses:

1. **`shopflow-sqlite`** — Anthropic's reference [`mcp-server-sqlite`](https://github.com/modelcontextprotocol/servers), launched via `uvx` (6 tools)
2. **`datapilot-dq`** — *your own* MCP server (Module 07), 4 data-quality tools, ~60 lines of FastMCP
3. **`datapilot-rag`** — *your other own* MCP server (Module 09), 2 semantic-search tools backed by ChromaDB over `docs/*.md`

The DQ and RAG servers are later registered in **Claude Desktop** so a
second, unrelated agent can call your tools without code changes. That
is the whole point of MCP — *write the tool once, every agent gets it*.

---

## 2. Tech stack — every piece, and why

| Layer | Choice | Why |
|---|---|---|
| **LLM** | Groq `openai/gpt-oss-20b` | Free, fast, clean OpenAI-style tool calling. Swap by editing `.env`. |
| **Agent runtime** | `langgraph.prebuilt.create_react_agent` | Modern LangChain agent API. Replaces the deprecated `AgentExecutor`. Handles the think → call → observe → think loop. |
| **Memory** | `langchain_core.messages` history kept on the `ChatAgent` instance | One conversation per Streamlit session. Enables follow-ups like *"and orders?"* |
| **Tool protocol** | **Model Context Protocol (MCP)** | Industry-standard JSON-RPC contract for tool servers. Used by Anthropic, Cursor, Zed, Continue. |
| **MCP client** | `langchain-mcp-adapters` (`MultiServerMCPClient`) | Spawns servers, discovers their tools, wraps them as LangChain `BaseTool` objects. |
| **MCP server framework** | `mcp` package (FastMCP) | Decorator-based: `@mcp.tool()` turns a function into a discoverable tool. |
| **Off-the-shelf MCP server** | `mcp-server-sqlite` via `uvx` | Don't reinvent SQL execution; reuse the published one. |
| **Vector store (RAG)** | `chromadb` with bundled ONNX `all-MiniLM-L6-v2` | File-based, no server, no torch. ~120MB embedding model auto-downloaded. |
| **UI** | Streamlit + Plotly | Lowest friction for chat + charts. |
| **Database** | SQLite (`shopflow.db`) | Zero-setup, file-based, works offline. Architecture is portable to Postgres/Snowflake by swapping the MCP server. |
| **Synthetic data** | `Faker` | 800 customers, 4 000 orders, 7 tables, repeatable seed (42). |
| **Testing** | pytest (17 cases) + `smoke_e2e.py` | Unit-tests the guardrail and chart picker; smoke-tests the live agent. |
| **Packaging / launcher** | `run.ps1` + `uv` | One command from clone → running app on Windows. |

---

## 3. Core concepts (start here if you're new)

### 3.1 LLM
A large language model that, given text, generates more text. Modern LLMs
also produce **structured tool calls** (a JSON object naming a function and
its arguments). DataPilot uses Groq's hosted `gpt-oss-20b`.

### 3.2 Tool calling
Instead of asking the LLM to *answer* a question directly, we let it
**ask for help**: *"please run `read_query` with this SQL."* Our code
runs the SQL, returns rows, and the LLM uses them to compose the answer.
This is how an LLM stops hallucinating numbers.

### 3.3 ReAct loop (Reason + Act)
The pattern that makes an LLM behave like an agent:

```
        ┌──────────────────────────────┐
        │  think  →  call tool         │
        │     ↑                ↓       │
        │  use result   ←   observe    │
        └──────────────────────────────┘
```

The LLM keeps looping until it has enough information to answer. LangGraph's
`create_react_agent` implements this for us — we never write the loop ourselves.

### 3.4 Model Context Protocol (MCP)
A small JSON-RPC contract that any LLM client can speak to any tool server,
regardless of language. An MCP server exposes:
- `tools/list` — *"what can you do?"*
- `tools/call` — *"please do this with these arguments"*

Each server runs in its **own process**. Communication is over stdin/stdout
(stdio transport). Spawning a server is one line in `mcp.json`.

**Why this matters:** the same `datapilot-dq` server runs unchanged in
your Streamlit app *and* in Claude Desktop. The tool is portable; the
client is replaceable.

### 3.5 Guardrails
Two layers in DataPilot:
1. **Whitelist** — the agent is only handed `list_tables`, `describe_table`,
   `read_query`, plus the 4 DQ tools. It literally does not see
   `write_query`, `create_table`, or `drop`. They cannot be invoked.
2. **SQL sanitiser** — the `read_query` tool input is wrapped: rejects DDL/DML,
   rejects multi-statement queries, auto-injects `LIMIT 1000` if missing.

### 3.6 Data-quality (DQ)
Production analytics agents must answer questions about the **state of the
data**, not just its values: *is it fresh?* *are there nulls?* *duplicates?*
DataPilot's `datapilot-dq` server exposes these as first-class tools the
agent can pick on its own.

---

## 4. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Streamlit UI                                                  │
│  ─ chat input ─ table ─ Plotly chart ─ sidebar (badges, cost)  │
└──────────────────────────────┬─────────────────────────────────┘
                               │  user types a question
                               ▼
┌────────────────────────────────────────────────────────────────┐
│  ChatAgent  (solution/app/chat_agent.py)                       │
│  ─ LangGraph ReAct loop                                        │
│  ─ Conversation memory (per Streamlit session)                 │
│  ─ Guardrail wrapper around read_query                         │
└──────────────────────────────┬─────────────────────────────────┘
                               │  JSON-RPC over stdio
                               ▼
┌─────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ shopflow-sqlite │   │  datapilot-dq    │   │  datapilot-rag   │
│ (uvx, 6 tools)  │   │ (FastMCP, 4)     │   │ (FastMCP, 2)     │
│ list_tables,    │   │ count_rows,      │   │ search_docs,     │
│ describe_table, │   │ check_freshness, │   │ list_docs        │
│ read_query, ... │   │ check_nulls,     │   │                  │
│                 │   │ check_duplicates │   │                  │
└────┬────────────┘   └────┬─────────────┘   └────┬─────────────┘
     │                  │                       │
     └──────┬───────────┘                       │
            ▼                                   ▼
   ┌──────────────┐               ┌────────────────────┐
   │  shopflow.db │               │ data/rag.chroma/   │
   │  800 cust    │               │ (vector index over │
   │  4 000 ord   │               │  docs/*.md)        │
   └──────────────┘               └────────────────────┘
```

**Both `datapilot-dq` and `datapilot-rag` are also registered in Claude
Desktop** via `claude_desktop_config.example.json` (Module 10). Two
clients, two custom tools each.

---

## 5. The data: ShopFlow

A synthetic e-commerce warehouse generated by [data/build_shopflow.py](data/build_shopflow.py)
(seed = 42, fully deterministic).

| Table | Rows | Why it exists |
|---|---|---|
| `customers` | 800 | Identity, country, signup date, segment (new/returning/vip) |
| `products` | 120 | 7 categories, price + cost, active flag |
| `orders` | 4 000 | order_date, channel, status, total_amount |
| `order_items` | ~12 000 | the line items — needed for category revenue |
| `returns` | ~400 | refunds with reasons |
| `support_tickets` | ~600 | category + priority + resolved flag |
| `web_sessions` | ~5 000 | conversion funnel |

Realistic enough to ask *"refund rate by category"*, *"AOV by channel"*,
*"top 5 products by revenue last month"*.

---

## 6. Repository layout

```
.
├── data/
│   ├── build_shopflow.py              # synthetic-data generator
│   ├── shopflow.db                    # generated SQLite warehouse
│   └── rag.chroma/                    # generated vector index (Module 09)
│
├── docs/                              # RAG corpus (7 short markdown files)
│
├── solution/                          # finished reference app
│   ├── app/
│   │   ├── streamlit_app.py           # the UI
│   │   ├── chat_agent.py              # LangGraph ReAct agent + memory
│   │   ├── mcp_clients.py             # spawns the MCP servers
│   │   ├── guardrails.py              # SQL sanitiser
│   │   ├── charts.py                  # auto line/bar/none
│   │   ├── llm.py                     # Groq client factory
│   │   └── config/mcp.json            # MCP server registry (3 entries)
│   └── mcp_servers/
│       ├── dq_server.py               # in-house MCP server (4 DQ tools)
│       ├── rag_server.py              # in-house MCP server (2 RAG tools)
│       └── build_rag_index.py         # builds data/rag.chroma/ from docs/
│
├── student/
│   ├── app/streamlit_app.py           # Day-0 empty shell
│   ├── README.md                      # module index
│   └── MODULE_00_*.md … MODULE_10_*.md  # 11 build cards (one per module)
│
├── tests/                             # pytest — guardrails + charts
├── facilitator/RUN_OF_SHOW.md         # instructor's minute-by-minute script
├── checkpoints/README.md              # "I fell behind, copy this file" map
├── claude_desktop_config.example.json # template for Module 10
├── smoke_e2e.py                       # end-to-end agent harness
├── requirements.txt
├── run.ps1                            # one-shot launcher (Windows)
└── README.md                          # this file
```

---

## 7. Quick start

```powershell
git clone <repo>
cd session7-sql-data-agent
copy .env.example .env          # paste your free Groq key (https://console.groq.com/keys)
python data\build_shopflow.py   # builds shopflow.db (~1 s)
.\run.ps1                       # auto-installs uv, creates .venv, installs deps, launches Streamlit
```

Defaults to the **student Day-0 shell** at <http://localhost:8501>.

To launch the finished reference app instead:
```powershell
$env:DATAPILOT_APP = "solution"
.\run.ps1
```

To run both in parallel (different ports):
```powershell
.\.venv\Scripts\streamlit.exe run student\app\streamlit_app.py    --server.port 8601
.\.venv\Scripts\streamlit.exe run solution\app\streamlit_app.py   --server.port 8602
```

---

## 8. The webinar script — 11 modules, each visible in the UI

The whole project is structured so every single module produces a **visible
change in the running Streamlit app**. After each module, students refresh
the browser and see one new thing. This is the entire build, in order.

> **Setup for the instructor before module 0:** clone the repo, run `.\run.ps1`
> once to create `.venv` and `data/shopflow.db`, leave a terminal open with
> `streamlit run student\app\streamlit_app.py` running. Have the
> [solution/](solution/) folder bookmarked for copy-paste fallback.

---

### Phase 1 — Foundation (Modules 0 → 5)

#### **Module 0 — Setup** (10 min)

**Concept introduced:** Python venv, pinned requirements, `.env` for secrets,
synthetic data as a shared baseline.

**Files touched:** `.env` (created from `.env.example`), `data/shopflow.db` (built).

**Live commands:**
```powershell
copy .env.example .env       # paste your GROQ_API_KEY
python data\build_shopflow.py
.\run.ps1                    # launches student app
```

**What students see in Streamlit:** the **Day-0 shell** — a sidebar listing
the 11 modules they're about to build. Empty main pane with the message
*"Open the first PART card and start building."*

**Talking point:** *"Notice there's no chat box, no tools, nothing. By
module 10 this same file will be a working analytics agent."*

---

#### **Module 1 — MCP wiring** (15 min)

**Concept introduced:** **MCP** — the agent does not own its tools. We
declare a server in `mcp.json`, spawn it as a subprocess, and ask it
*"what tools do you have?"* Zero tool code on our side.

**Files created:**
- [solution/app/config/mcp.json](solution/app/config/mcp.json) — registers `shopflow-sqlite`
- [solution/app/mcp_clients.py](solution/app/mcp_clients.py) — `load_mcp_tools()` returns `(client, tools)`

**Code to write live (mcp.json):**
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

**Code to write live (mcp_clients.py — abridged):**
```python
async def _gather():
    cfg = _load_config()                                    # reads mcp.json
    client = MultiServerMCPClient(cfg["mcpServers"])         # spawns subprocesses
    tools = await client.get_tools()                        # asks each "what can you do?"
    return client, tools
```

**Update student `streamlit_app.py`:** add a sidebar block that calls
`load_mcp_tools()` and lists tool names by server.

**What students see:** the sidebar now shows
**`🔌 Connected MCP servers · shopflow-sqlite · 6 tools`** with an expander
listing `list_tables`, `describe_table`, `read_query`, `write_query`,
`create_table`, `append_insight`.

**Talking point:** *"Six tools, zero lines of tool code in our repo. The
server is a separate process — kill it and our app gracefully reports zero
tools."*

---

#### **Module 2 — Chat agent (the core)** ⭐ (25 min)

**Concept introduced:** **ReAct loop**, **tool calling**, **conversational
memory**, **system-prompt steering**.

**Files created:**
- [solution/app/llm.py](solution/app/llm.py) — Groq factory
- [solution/app/chat_agent.py](solution/app/chat_agent.py) — `ChatAgent` class

**Code to write live (chat_agent.py — abridged):**
```python
SYSTEM_PROMPT = """You are DataPilot, an analytics colleague.
Schema: customers, products, orders, order_items, ...
Workflow:
  1. Skim schema with list_tables/describe_table only if uncertain.
  2. Write ONE SQL SELECT and call read_query.
  3. As soon as you have numbers, STOP and answer in <= 3 sentences.
"""

class ChatAgent:
    def __init__(self, tools):
        self.llm = get_llm()
        self.graph = create_react_agent(self.llm, tools, prompt=SYSTEM_PROMPT)
        self.history = []

    def ask(self, question):
        messages = self.history + [HumanMessage(content=question)]
        state = asyncio.run(self.graph.ainvoke({"messages": messages},
                                               config={"recursion_limit": 25}))
        # ... extract final answer + tool-call trace ...
```

**Update `streamlit_app.py`:** add `st.chat_input` + render history with
`st.chat_message`. Wire `agent.ask(prompt)` and display `turn.answer`.
Add a "🔍 Show steps" expander listing each tool call.

**What students see:**
- A real chat box appears.
- Type *"how many customers do we have?"* → after a few seconds:
  *"We have 800 customers."*
- Expand "🔍 Show steps" → see the agent picked `list_tables`, then
  `read_query` with `SELECT COUNT(*) FROM customers`.
- Type *"and orders?"* → *"There are 4 000 orders."* (memory works.)

**Talking point:** *"We never wrote SQL. We never registered a tool. The
LLM read our schema hint, picked `read_query`, wrote the SQL, ran it,
and summarised the result. The conversation memory is a Python list."*

---

#### **Module 3 — Guardrails** (15 min)

**Concept introduced:** Two layers of safety — **tool whitelist** (the
model literally cannot see dangerous tools) and a **SQL sanitiser**
(everything that does land in `read_query` is rewritten safe).

**File created:** [solution/app/guardrails.py](solution/app/guardrails.py).

**Code to write live (guardrails.py):**
```python
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|truncate|"
                        r"create|replace|grant|revoke|attach|detach|"
                        r"pragma|vacuum|reindex)\b", re.IGNORECASE)
_MULTI_STMT = re.compile(r";\s*\S")

def validate_and_fix(sql, cfg=None):
    s = sql.strip().rstrip(";").strip()
    if _MULTI_STMT.search(s):  raise GuardrailError("Multi-statement")
    if _FORBIDDEN.search(s):   raise GuardrailError("Read-only only")
    if not re.match(r"^\s*(select|with)\b", s, re.I):
        raise GuardrailError("Must start with SELECT/WITH")
    if not re.search(r"\blimit\b", s, re.I):
        s = f"{s}\nLIMIT 1000"
    return s
```

**Wire it in `chat_agent.py`:**
```python
SAFE_TOOL_NAMES = {"list_tables","describe_table","read_query",
                   "check_freshness","check_nulls","check_duplicates","count_rows"}

def filter_and_guard(tools):
    kept = [t for t in tools if t.name in SAFE_TOOL_NAMES]
    for t in kept:
        if t.name == "read_query":
            _wrap_read_query(t)            # sanitise before SQL leaves our process
    return kept
```

**Tests to run live:** `pytest tests/test_guardrails.py -v` → **11 passing**.

**What students see:**
- The sidebar's `shopflow-sqlite` expander: `write_query`, `create_table`,
  `append_insight` are **gone** (or marked ✗). Only safe tools remain.
- Type *"DROP TABLE customers"* → the agent tries, the wrapper returns
  `GUARDRAIL BLOCK: Only read-only SELECT/WITH queries are allowed.`,
  the agent recovers and answers something like *"The table 'customers'
  still exists with 800 rows."*

**Talking point:** *"Defence in depth. The whitelist makes the bad action
inconceivable to the model. The sanitiser catches the case where the
model gets clever or another developer adds a write tool by mistake."*

---

#### **Module 4 — Charts** (10 min)

**Concept introduced:** **Smart-pick** chart selection. No chart for a
scalar answer. Line for time series. Bar for 2–25 categories. Otherwise
nothing — *"silence beats a misleading chart."*

**File created:** [solution/app/charts.py](solution/app/charts.py).

**Code to write live:**
```python
def auto_chart(df):
    if df is None or df.empty or df.shape[1] < 2 or df.shape[0] < 2:
        return None
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols: return None
    y = numeric_cols[0]
    # date × number → line
    for c in df.columns:
        if c != y and _is_datey(df[c]):
            return px.line(df.sort_values(c), x=c, y=y, markers=True, ...)
    # categorical (2–25 rows) → bar
    cat_cols = [c for c in df.columns if c != y and _is_stringy(df[c])]
    if cat_cols and 2 <= df.shape[0] <= 25:
        return px.bar(df, x=cat_cols[0], y=y, ...)
    return None
```

**Wire it in `streamlit_app.py`** after the assistant's answer: parse the
`read_query` result rows back into a DataFrame, call `auto_chart`, render
with `st.plotly_chart(fig)` if not None.

**What students see:**
- Type *"top 5 product categories by revenue"* → answer + a 5-row table +
  a **bar chart** (Electronics / Home & Kitchen / Sports / Toys / Apparel
  on the x-axis).
- Type *"how many customers"* → answer + **no chart** (scalar).
- Type *"orders per month in 2026"* → answer + a **line chart**.

**Talking point:** *"Three rules. Twenty lines. The agent doesn't even
know about charts — the UI auto-picks based on the shape of the result."*

---

#### **Module 5 — Configuration tour** (15 min)

**Concept introduced:** **Configuration over code.** The whole architecture
swaps databases by editing one JSON file.

**No new code.** Walk students through `mcp.json` line by line:

```json
"shopflow-sqlite": {
  "command": "uvx",
  "args": ["mcp-server-sqlite", "--db-path", "${SHOPFLOW_DB}"],
  "transport": "stdio"
}
```

Show how to swap to a Postgres MCP server (4-line diff):
```json
"shopflow-postgres": {
  "command": "uvx",
  "args": ["mcp-server-postgres", "--connection-string", "${PG_URL}"],
  "transport": "stdio"
}
```

**What students see:** add a fake second entry, restart, sidebar shows
**2 servers**. Remove it, restart, back to 1. Behaviour change with zero
Python edits.

**Talking point:** *"In production you swap warehouses, not codebases.
The agent code never knew or cared about SQLite specifically."*

---

> **Phase 1 exit:** working Streamlit + ReAct agent + 1 MCP server +
> guardrail + auto-charts. 11 unit tests green. Three demo questions
> verified live.

---

### Phase 2 — Platform (Modules 6 → 11)

#### **Module 6 — Recap and smoke** (10 min)

**Concept introduced:** A runnable **smoke harness** that exercises the
agent end-to-end without the UI.

**File:** [smoke_e2e.py](smoke_e2e.py) (already in repo). 4 questions covering:
schema discovery, follow-up memory, data quality, malicious prompt.

**Live command:**
```powershell
python smoke_e2e.py
```

**What students see:** terminal prints `Q1`, `Q2`, `Q3`, `Q4` with answer
+ tool-call count + latency. All 4 pass on `gpt-oss-20b`.

**Talking point:** *"This is the contract you protect when you make
changes. Run this before every commit."*

---

#### **Module 7 — Author your own MCP server** ⭐ (25 min)

**Concept introduced:** **Tool authoring.** FastMCP turns a Python
function into a discoverable tool with one decorator. ~60 lines = a real
MCP server.

**File created:** [solution/mcp_servers/dq_server.py](solution/mcp_servers/dq_server.py).

**Code to write live:**
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("datapilot-dq")

@mcp.tool()
def count_rows(table: str) -> str:
    """Return the row count of `table`. Quick health-check tool."""
    with sqlite3.connect(DB_PATH) as c:
        n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return f"{table}: {n} rows"

@mcp.tool()
def check_freshness(table: str, ts_column: str | None = None) -> str:
    """How fresh is `table`? Auto-detects timestamp column if omitted."""
    # ... finds latest timestamp, returns "[OK]" or "[STALE]" + age in hours

@mcp.tool()
def check_nulls(table: str, column: str) -> str: ...
@mcp.tool()
def check_duplicates(table: str, key_columns: str) -> str: ...

if __name__ == "__main__":
    mcp.run()
```

**Test the server standalone first** (no agent involved):
```powershell
python solution\mcp_servers\dq_server.py data\shopflow.db
```

**Then register it in `mcp.json`:**
```json
"datapilot-dq": {
  "command": "python",
  "args": ["solution/mcp_servers/dq_server.py", "${SHOPFLOW_DB}"],
  "transport": "stdio"
}
```

Add the 4 tool names to `SAFE_TOOL_NAMES` in `chat_agent.py`.

**What students see:**
- Sidebar now shows **two** MCP servers: `shopflow-sqlite · 6 tools` AND
  `datapilot-dq · 4 tools`.
- Ask *"is the orders data fresh?"* → the agent picks `check_freshness`
  (not SQL) and answers *"Orders is STALE — latest order_date is
  2026-04-30, ~283 hours ago."*

**Talking point:** *"You just published a tool. Anything that speaks MCP —
our app, Claude Desktop, Cursor, internal copilots — gets it for free."*

---

#### **Module 8 — Health snapshot** (15 min)

**Concept introduced:** Calling MCP tools **directly from the UI**, not
through the agent. Useful for "always-on" status panels.

**Update `streamlit_app.py` sidebar:**
```python
if st.button("Run quick checks", width="stretch"):
    tool_map = {t.name: t for t in raw_tools}
    for table in ("orders", "customers", "products"):
        res = asyncio.run(tool_map["count_rows"].ainvoke({"table": table}))
        st.session_state.health[f"rows {table}"] = _flatten(res)
    res = asyncio.run(tool_map["check_freshness"].ainvoke({"table": "orders"}))
    st.session_state.health["freshness orders"] = _flatten(res)

# Render with red/green badges
for k, v in st.session_state.health.items():
    badge = "🟢" if "OK" in v or "rows" in k else \
            "🔴" if "STALE" in v or "FAIL" in v else "🟡"
    st.caption(f"{badge} {v}")
```

**What students see:** new **🩺 Health snapshot** section in sidebar with a
*Run quick checks* button. After clicking:
- 🟢 orders: 4 000 rows
- 🟢 customers: 800 rows
- 🟢 products: 120 rows
- 🔴 [STALE] orders.order_date: latest 2026-04-30 (283 h ago)

**Talking point:** *"The same MCP tools serve two consumers — the agent
when a user asks, and a one-click button for proactive monitoring."*

---

#### **Module 9 — RAG over your docs** (25 min)

**Concept introduced:** A **second** in-house MCP server, in a completely
different shape from the DQ one. The agent now answers semantic questions
like *"what does VIP mean?"* by searching your `docs/*.md` corpus.

**Files created:**
- [solution/mcp_servers/build_rag_index.py](solution/mcp_servers/build_rag_index.py) — one-shot indexer.
- [solution/mcp_servers/rag_server.py](solution/mcp_servers/rag_server.py) — `@mcp.tool() search_docs` + `list_docs`.

**Stack:** ChromaDB with its bundled ONNX `all-MiniLM-L6-v2` embedding —
no torch, no API key, the model auto-downloads on first index (~120MB).

```python
@mcp.tool()
def search_docs(query: str, k: int = 3) -> str:
    res = collection.query(query_texts=[query], n_results=k)
    return "\n---\n".join(res["documents"][0])
```

**Wired into the agent** by adding a third entry to
[solution/app/config/mcp.json](solution/app/config/mcp.json) and adding
`search_docs` / `list_docs` to the whitelist in `chat_agent.py`.

**What students see:** ask *"what is a VIP customer?"* → the agent calls
`search_docs`, grounds its answer in `docs/02_segments_glossary.md`, and
cites a snippet. The sidebar now shows **three** MCP servers.

**Talking point:** *"Same MCP framework, totally different domain — SQL
last hour, vector search this hour. The agent picks the right tool
without us writing a single routing rule."*

---

#### **Module 10 — Cross-client portability with Claude Desktop** 🎉 (15 min)

**Concept introduced:** **Both** of your in-house MCP servers running in
**two** completely different agents. This is the punchline of the whole
workshop.

**File:** [claude_desktop_config.example.json](claude_desktop_config.example.json) (template provided).

**Live steps:**
1. Open Claude Desktop's config file (`%APPDATA%\Claude\claude_desktop_config.json`).
2. Paste the `datapilot-dq` and `datapilot-rag` blocks from the example,
   adjusting paths to absolute.
3. Quit Claude. Re-open. The 🔌 tools icon now shows `datapilot-dq` (4 tools)
   and `datapilot-rag` (2 tools).
4. Ask Claude: *"is the orders table fresh, and what does VIP mean?"* →
   Claude calls **both of your servers** in one turn and answers using
   results from each.

**What students see:** the *exact same DQ and RAG outputs* showing up in
**Claude Desktop**, called by **Claude's own ReAct loop**, hitting **your
two Python servers**. Side-by-side both windows is the demo.

**Talking point:** *"Two completely unrelated agents — built by different
teams, using different LLMs — now share both of your tools. That's the
leverage MCP unlocks."*

---

> **Phase 2 exit:** three MCP servers (one off-the-shelf, two you built),
> sidebar health snapshot, semantic doc search, cross-client demo.
> Tests green. End-to-end smoke pass.

---

## 9. Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # 17 passed
.\.venv\Scripts\python.exe smoke_e2e.py          # Q1/Q2/Q3/Q4 all pass on gpt-oss-20b
.\run.ps1                                        # student app boots
$env:DATAPILOT_APP="solution"; .\run.ps1         # solution app boots, sidebar shows 2 MCP servers
```

Browser walkthrough (manual smoke):
1. *"how many customers and orders"* → "800 customers and 4 000 orders"
2. *"top 5 product categories by revenue"* → table + bar chart
3. *"is the orders data fresh?"* → STALE flag from `check_freshness`
4. *"DROP TABLE customers"* → `GUARDRAIL BLOCK`, agent recovers,
   table count unchanged

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Spawning MCP servers...` hangs forever | `uvx` not on PATH or no internet on first run | Run `.\run.ps1` once with internet — it pre-fetches `mcp-server-sqlite`. |
| Sidebar shows `0 tools` | MCP server crashed at startup | Check terminal logs for the subprocess; usually a wrong `SHOPFLOW_DB` path. |
| `413 rate_limit_exceeded` from Groq | You're on `llama-3.1-8b-instant` (6k TPM cap) | In `.env` set `GROQ_MODEL=openai/gpt-oss-20b` (the workshop default). |
| Chart never appears | Result is a single scalar row | Working as intended — `auto_chart` returns `None` for scalars. |
| `Sorry, need more steps to process this request` | `recursion_limit` too low for a JOIN-heavy question | Already bumped to 25 in `chat_agent.py`. If you removed the schema hint from the system prompt, put it back. |
| `Table (1 rows)` for a multi-row result | The MCP content-block wrapper wasn't peeled | See `_maybe_extract_table` in `streamlit_app.py` — it now unwraps `[{type,text,id}]` first. |
| Streamlit complains about `use_container_width` | Cosmetic deprecation (deadline 2025-12-31) | Replace with `width='stretch'`. |
| OneDrive / Claude Desktop config edits don't take effect | Claude was still running | Quit Claude **completely** (system tray) and reopen. |

---

## For instructors

- Minute-by-minute script: [facilitator/RUN_OF_SHOW.md](facilitator/RUN_OF_SHOW.md)
- Recovery cheatsheet (which file to copy if a student falls behind):
  [checkpoints/README.md](checkpoints/README.md)
- Slide deck (auto-generated, 30 slides with diagrams):
  [slides/datapilot_workshop.pptx](slides/datapilot_workshop.pptx)
  ```powershell
  .\.venv\Scripts\python.exe slides\build_pptx.py    # rebuild after edits
  ```
