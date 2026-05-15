# Module 03 — Guardrails (15 min)

> Goal: even if the LLM tries `DROP TABLE customers`, your app refuses.

## 1. Create `student/app/guardrails.py`
```python
import re
from dataclasses import dataclass, field

# Deny-list of write / DDL / admin keywords. \b = word boundary, so we match
# 'delete' but NOT 'deleted_at'. Compiled once at import for speed.
DANGEROUS = re.compile(
    r"\b(drop|delete|update|insert|alter|truncate|create|attach|detach|pragma|vacuum|replace)\b",
    re.IGNORECASE,
)
# Detects a semicolon followed by more non-whitespace -> a 2nd statement.
# After stripping one trailing ';' we use this to catch 'SELECT 1; DROP ...'
MULTI_STMT = re.compile(r";\s*\S")

class GuardrailError(ValueError):
    """Raised when SQL fails a safety check. Subclasses ValueError on purpose."""
    pass

@dataclass
class GuardrailConfig:
    # Hard ceiling we inject as LIMIT when the model forgets one.
    max_rows: int = 1000
    # Optional allow-list of tables that may appear after FROM/JOIN.
    allowed_tables: set[str] | None = None

def validate_and_fix(sql: str, cfg: GuardrailConfig | None = None) -> str:
    """Validate read-only SQL and inject LIMIT if missing.

    Returns the cleaned-up SQL. Raises GuardrailError on anything dangerous.
    Think of this as a firewall between the LLM and the database.
    """
    cfg = cfg or GuardrailConfig()
    # Normalise: trim whitespace + one trailing semicolon.
    s = sql.strip().rstrip(";").strip()
    if not s: raise GuardrailError("empty SQL")

    # Check 1 -- reject stacked statements like "SELECT 1; DROP ...".
    if MULTI_STMT.search(sql): raise GuardrailError("multiple statements")
    # Check 2 -- reject any write/DDL/admin keyword anywhere in the query.
    if DANGEROUS.search(s): raise GuardrailError("write/DDL keyword blocked")
    # Check 3 -- must START with SELECT or WITH (positive allow-list).
    if not re.match(r"^\s*(with|select)\b", s, re.IGNORECASE):
        raise GuardrailError("only SELECT / WITH allowed")

    # Check 4 -- optional table allow-list. Walks every FROM <name> and
    # rejects anything not on the list.
    if cfg.allowed_tables:
        for t in re.findall(r"\bfrom\s+([a-zA-Z_][\w]*)", s, re.IGNORECASE):
            if t.lower() not in {x.lower() for x in cfg.allowed_tables}:
                raise GuardrailError(f"table {t!r} not allowed")

    # Fix-up -- append LIMIT if the model forgot one, so an accidental giant
    # result set can't blow up the UI.
    if not re.search(r"\blimit\b", s, re.IGNORECASE):
        s += f" LIMIT {cfg.max_rows}"
    return s
```

## 2. Wrap the MCP `read_query` — full `student/app/chat_agent.py`

> 💡 **Two changes vs. Module 02:**
> 1. Filter `self.tools` through a `SAFE` allow-list so `write_query` /
>    `create_table` / `append_insight` are hidden from the model.
> 2. Monkey-patch the `read_query` tool's `coroutine` with a guarded version
>    that runs the SQL through `validate_and_fix()` first.
>
> Everything else (system prompt, `ainvoke`, message walker) is identical.

Replace the **entire** contents of `student/app/chat_agent.py` with:

```python
"""DataPilot chat agent — Module 03: tool allow-list + SQL guardrail."""
import time, asyncio, nest_asyncio
from dataclasses import dataclass, field

# LangGraph gives us a ready-made ReAct loop (reason -> act -> observe -> ...)
from langgraph.prebuilt import create_react_agent
# In-memory store for conversation state (per thread_id). Survives one app run.
from langgraph.checkpoint.memory import InMemorySaver
# LangChain message classes the agent reasons over.
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_llm
from app.mcp_clients import load_mcp_tools
# NEW in Module 03: the SQL firewall.
from app.guardrails import validate_and_fix, GuardrailError

# Streamlit already runs an event loop. Without this patch you'd hit
# 'RuntimeError: This event loop is already running' every chat turn.
nest_asyncio.apply()

SYSTEM = """You are DataPilot, a careful data analyst.
- Use list_tables / describe_table to discover schema before SELECTing.
- Always answer in 1-2 sentences plus a short table when relevant.
- Never invent columns. If a tool errors, fix and retry once.
"""

# Allow-list of tool names the LLM is even ALLOWED to see. Anything not here
# (e.g. write_query, create_table, append_insight) is hidden -> the model
# literally CAN'T pick it. Defence in depth alongside the SQL guardrail.
SAFE = {"read_query", "list_tables", "describe_table"}


@dataclass
class TurnResult:
    """Plain-data container for one chat turn. Easy for the UI to render."""
    answer: str
    tool_calls: list = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None


def _wrap_read_query(tool):
    """Wrap the MCP read_query tool's coroutine with the SQL guardrail.

    The model can call read_query freely; if its SQL is dangerous, the
    guardrail raises BEFORE the call ever leaves our process. From the
    LLM's perspective the tool just returned an error message it can
    react to and retry with safer SQL.
    """
    # Keep a reference to the ORIGINAL async impl -- we'll delegate to it
    # only after validation succeeds.
    original = tool.coroutine

    async def guarded(query: str, _orig=original, **kw):
        try:
            # Run the SQL through the firewall first.
            safe = validate_and_fix(query)
        except GuardrailError as e:
            # mcp-server-sqlite's read_query uses content_and_artifact
            # response shape -> must return a (content, artifact) tuple.
            # Returning (instead of raising) lets the LLM see the rejection
            # and try a corrected query on the next loop iteration.
            return f"GUARDRAIL BLOCK: {e}", None
        # SQL is clean -> forward to the real MCP tool.
        return await _orig(query=safe, **kw)

    # Monkey-patch the coroutine in place. The tool object identity is
    # unchanged, so any existing LangChain bindings stay valid.
    tool.coroutine = guarded
    return tool


class ChatAgent:
    """One agent instance per Streamlit session. Holds tools + memory."""

    def __init__(self):
        # 1. Spawn MCP servers ONCE.
        self.tools, _ = load_mcp_tools()

        # 2. Drop dangerous tools so the model can't even SEE them.
        #    Sidebar tools count will drop from 6 to 3.
        self.tools = [t for t in self.tools if t.name in SAFE]

        # 3. For the one tool that CAN touch the DB, install the guardrail.
        for t in self.tools:
            if t.name == "read_query":
                _wrap_read_query(t)

        # 4. Usual setup -- LLM, memory, graph.
        self.llm = get_llm()
        self.memory = InMemorySaver()
        self.graph = create_react_agent(
            self.llm, self.tools,
            checkpointer=self.memory,
            prompt=SystemMessage(SYSTEM),
        )
        self.thread = {"configurable": {"thread_id": "main"}}

    def ask(self, q: str) -> TurnResult:
        """Run one reason-act loop for the user's question."""
        t0 = time.time()
        try:
            # MCP tools are async-only (StructuredTool has no sync impl).
            # Drive the graph via ainvoke() and bridge to sync with asyncio.run().
            # nest_asyncio.apply() above lets this nest inside Streamlit's loop.
            state = asyncio.run(self.graph.ainvoke(
                {"messages": [HumanMessage(q)]}, self.thread))

            # Walk the messages and pair each tool call with its output
            # so the UI can show "this tool was called with these args, result was X".
            calls = []
            for m in state["messages"]:
                if hasattr(m, "tool_calls") and m.tool_calls:
                    for tc in m.tool_calls:
                        calls.append({"tool": tc["name"], "input": tc["args"], "output": ""})
                if m.__class__.__name__ == "ToolMessage" and calls:
                    calls[-1]["output"] = m.content

            return TurnResult(
                answer=state["messages"][-1].content,
                tool_calls=calls,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:
            # Surface ANY failure in the UI instead of crashing Streamlit.
            return TurnResult(answer="", error=f"{type(e).__name__}: {e}",
                              latency_ms=int((time.time() - t0) * 1000))
```

### What changed vs. Module 02 (diff at a glance)
1. **New import** — `from app.guardrails import validate_and_fix, GuardrailError`.
2. **New constant** — `SAFE = {"read_query", "list_tables", "describe_table"}`.
3. **New helper** — `_wrap_read_query(tool)` monkey-patches the tool's `coroutine`.
4. **In `__init__`** — filter `self.tools` through `SAFE`, then wrap `read_query`.
5. Everything else is byte-for-byte identical to Module 02.

## 2b. Make the sidebar show the *filtered* tools

The Module 02 sidebar called `load_mcp_tools()` directly, so it would still
display all 6 raw MCP tools even after the agent filtered them. Show what
the agent actually sees instead.

In `student/app/streamlit_app.py`, replace `get_tools_and_agent()` and the
sidebar block with:

```python
@st.cache_resource(show_spinner="Spawning MCP servers...")
def get_tools_and_agent():
    _, cfg = load_mcp_tools()       # cfg = {server: spec} for the sidebar
    agent = ChatAgent()             # agent owns the (filtered) tool list
    return agent.tools, cfg, agent  # show what the AGENT actually sees

tools, cfg, agent = get_tools_and_agent()

# Module 03: we render `agent.tools` (already passed through SAFE allow-list),
# so the count here matches what the LLM can actually call. Drops 6 -> 3.
with st.sidebar:
    st.header("MCP servers")
    for name in cfg:
        st.success(f"● {name}")
    with st.expander(f"Tools ({len(tools)})"):
        for t in tools:
            st.caption(f"`{t.name}` — {t.description[:60]}")
```

> ⚠️ **Restart Streamlit** after saving (Ctrl+C → re-run). `@st.cache_resource`
> in `streamlit_app.py` holds the OLD agent (without the guardrail) until you
> kill the process. The sidebar tools count is also cached.

## 3. Test it
```bash
pytest tests/test_guardrails.py -v
```
All 11 tests should pass.

## ✅ CHECK
- Sidebar **Tools** count drops from 6 → 3.
- Ask in chat: **"run this SQL: drop table customers"** → answer mentions
  `GUARDRAIL BLOCK` (or the agent refuses politely).
- The DB is untouched.
