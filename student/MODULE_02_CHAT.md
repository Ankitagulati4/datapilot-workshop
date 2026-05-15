# Module 02 — Chat agent with memory (25 min)

> Goal: a LangGraph ReAct agent that uses the MCP tools, remembers prior turns, and streams answers.

## 1. Create `student/app/chat_agent.py`
```python
import time, asyncio, nest_asyncio
from dataclasses import dataclass, field

# LangGraph gives us a ready-made ReAct loop (reason -> act -> observe -> ...)
from langgraph.prebuilt import create_react_agent
# In-memory store for conversation state (per thread_id). Survives one app run.
from langgraph.checkpoint.memory import InMemorySaver
# LangChain message classes the agent reasons over.
from langchain_core.messages import HumanMessage, SystemMessage

from app.llm import get_llm                # our LLM factory (Module 02 step 2)
from app.mcp_clients import load_mcp_tools  # the tools we discovered in Module 01

# Streamlit already runs an event loop. Without this patch you'd hit
# 'RuntimeError: This event loop is already running' every chat turn.
nest_asyncio.apply()

# The system prompt is the model's job description. We bake the rules of
# engagement here so the agent stays grounded and concise.
SYSTEM = """You are DataPilot, a careful data analyst.
- Use list_tables / describe_table to discover schema before SELECTing.
- Always answer in 1-2 sentences plus a short table when relevant.
- Never invent columns. If a tool errors, fix and retry once.
"""

@dataclass
class TurnResult:
    """Plain-data container for one chat turn. Easy for the UI to render."""
    answer: str
    tool_calls: list = field(default_factory=list)  # trace for 'Show steps'
    latency_ms: int = 0
    error: str | None = None

class ChatAgent:
    """One agent instance per Streamlit session. Holds tools + memory."""

    def __init__(self):
        # Spawn MCP servers ONCE and reuse the tools for every turn.
        self.tools, _ = load_mcp_tools()
        # Temperature 0 -> deterministic SQL (no creative drift).
        self.llm = get_llm()
        # Checkpointer = the agent's memory backend. Same thread_id -> same history.
        self.memory = InMemorySaver()
        # Compile the ReAct graph: LLM picks tool, tool result feeds back, repeat
        # until the LLM produces a final answer with no more tool calls.
        self.graph = create_react_agent(
            self.llm, self.tools,
            checkpointer=self.memory,
            prompt=SystemMessage(SYSTEM),
        )
        # All turns in this session share thread_id='main' -> they share memory.
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
                    # Attach the ToolMessage's content to the most recent open call.
                    calls[-1]["output"] = m.content

            return TurnResult(
                # Last message is the assistant's final answer.
                answer=state["messages"][-1].content,
                tool_calls=calls,
                latency_ms=int((time.time()-t0)*1000),
            )
        except Exception as e:
            # Surface ANY failure in the UI instead of crashing Streamlit.
            return TurnResult(answer="", error=f"{type(e).__name__}: {e}",
                              latency_ms=int((time.time()-t0)*1000))
```

## 2. Create `student/app/llm.py`
```python
import os
# python-dotenv reads .env and copies key=value pairs into os.environ.
# Keeps secrets like GROQ_API_KEY out of source control.
from dotenv import load_dotenv
# LangChain wrapper around Groq's OpenAI-compatible API.
# Swappable later for ChatOpenAI / ChatAnthropic with no other code changes.
from langchain_groq import ChatGroq

# Load env vars once at import time.
load_dotenv()

def get_llm():
    """Return a configured ChatGroq instance. Fail loudly if the key is missing."""
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Set GROQ_API_KEY in .env")
    # Default model is a small fast OSS model; override via GROQ_MODEL=...
    # temperature=0 -> deterministic answers (essential for SQL/analytics).
    return ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
                    temperature=0)
```

## 3. Wire chat into the UI — full `student/app/streamlit_app.py`

> 💡 **Do NOT touch `student/app/mcp_clients.py` in this module.** The version
> you wrote in Module 01 already returns `(tools, cfg)`, which is exactly
> what this UI and `chat_agent.py` expect. If you copy a different version
> from `solution/` you will get `TypeError: 'MultiServerMCPClient' object
> is not iterable` because the shapes don't match.

Replace the **entire** contents of `student/app/streamlit_app.py` with:

```python
"""DataPilot — Module 02: chat agent wired into the UI."""

# --- import path shim -------------------------------------------------------
# Streamlit launches this file from the repo root, so `from app.foo import ...`
# would fail with ModuleNotFoundError. Add this file's parent (student/) to
# sys.path so `app` is an importable top-level package.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# ---------------------------------------------------------------------------

import streamlit as st

from app.mcp_clients import load_mcp_tools
from app.chat_agent import ChatAgent

# --- Page chrome ------------------------------------------------------------
st.set_page_config(page_title="DataPilot (student)", page_icon="🛠️", layout="wide")
st.title("🛠️ DataPilot — let's build it")
st.caption("Module 02: chat agent with memory.")

# --- One-time setup: spawn MCP servers, build the agent --------------------
# st.cache_resource keeps ONE shared instance per Streamlit session, so we
# don't respawn subprocesses or rebuild the LangGraph on every UI rerun.
@st.cache_resource(show_spinner="Spawning MCP servers...")
def get_tools_and_agent():
    tools, cfg = load_mcp_tools()   # tools = list[BaseTool], cfg = {server: spec}
    agent = ChatAgent()             # agent loads its own tools internally too
    return tools, cfg, agent

tools, cfg, agent = get_tools_and_agent()

# --- Sidebar: MCP server + tool list (from Module 01) ----------------------
with st.sidebar:
    st.header("MCP servers")
    for name in cfg:
        st.success(f"● {name}")
    with st.expander(f"Tools ({len(tools)})"):
        for t in tools:
            st.caption(f"`{t.name}` — {t.description[:60]}")

# --- Chat history (separate from the agent's LangGraph memory) -------------
# This list is just so we can re-render past bubbles after every Streamlit
# rerun. The agent's *real* memory lives in InMemorySaver inside ChatAgent.
if "history" not in st.session_state:
    st.session_state.history = []

# Replay history on every rerun (Streamlit re-executes the whole script).
for h in st.session_state.history:
    with st.chat_message(h["role"]):
        st.markdown(h["content"])

# --- Input box + one chat turn ---------------------------------------------
# Walrus operator: read the chat input; truthy only when user actually submits.
if q := st.chat_input("Ask about the data..."):
    # 1. Record + render the user's bubble.
    st.session_state.history.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    # 2. Render the assistant's bubble with a spinner while the agent thinks.
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            r = agent.ask(q)

        # Show error OR answer (TurnResult always has one).
        st.markdown(r.error or r.answer)

        # Collapsible trace: how many tools were called, latency, what they ran.
        with st.expander(f"steps · {len(r.tool_calls)} tool calls · {r.latency_ms} ms"):
            for c in r.tool_calls:
                st.code(f"{c['tool']}({c['input']})", language="python")
                if c.get("output"):
                    st.code(str(c["output"])[:600], language="text")

    # 3. Persist for the next rerun.
    st.session_state.history.append({"role": "assistant", "content": r.error or r.answer})
```

### Why each block exists
- **Path shim** — Streamlit's cwd is the repo root, so `app` isn't importable without it.
- **`@st.cache_resource`** — without this, every keystroke would respawn the MCP subprocesses.
- **Sidebar** — same code you wrote in Module 01; kept so students can see the integration is still alive.
- **`st.session_state.history`** — needed because Streamlit re-runs the whole script on every interaction; we need to remember past bubbles ourselves.
- **`if q := st.chat_input(...)`** — the walrus operator: assigns and tests in one expression.

## ✅ CHECK
- Ask: **"how many customers do we have?"** → `800`
- Follow-up: **"and orders?"** → `4000` (memory kept context)
- Expand the steps panel — you should see `list_tables`, `describe_table`, `count_rows` calls.
