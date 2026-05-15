# Module 02 — Chat agent with memory (25 min)

> Goal: a LangGraph ReAct agent that uses the MCP tools, remembers prior turns, and streams answers.

## 1. Create `student/app/chat_agent.py`
```python
import time, asyncio, nest_asyncio
from dataclasses import dataclass, field
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, SystemMessage
from app.llm import get_llm
from app.mcp_clients import load_mcp_tools

nest_asyncio.apply()

SYSTEM = """You are DataPilot, a careful data analyst.
- Use list_tables / describe_table to discover schema before SELECTing.
- Always answer in 1-2 sentences plus a short table when relevant.
- Never invent columns. If a tool errors, fix and retry once.
"""

@dataclass
class TurnResult:
    answer: str
    tool_calls: list = field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None

class ChatAgent:
    def __init__(self):
        self.tools, _ = load_mcp_tools()
        self.llm = get_llm()
        self.memory = InMemorySaver()
        self.graph = create_react_agent(
            self.llm, self.tools,
            checkpointer=self.memory,
            prompt=SystemMessage(SYSTEM),
        )
        self.thread = {"configurable": {"thread_id": "main"}}

    def ask(self, q: str) -> TurnResult:
        t0 = time.time()
        try:
            state = self.graph.invoke(
                {"messages": [HumanMessage(q)]}, self.thread)
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
                latency_ms=int((time.time()-t0)*1000),
            )
        except Exception as e:
            return TurnResult(answer="", error=f"{type(e).__name__}: {e}",
                              latency_ms=int((time.time()-t0)*1000))
```

## 2. Create `student/app/llm.py`
```python
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
load_dotenv()

def get_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Set GROQ_API_KEY in .env")
    return ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
                    temperature=0)
```

## 3. Wire chat into the UI
In `streamlit_app.py`:
```python
from app.chat_agent import ChatAgent

@st.cache_resource
def get_agent():
    return ChatAgent()

agent = get_agent()

if "history" not in st.session_state:
    st.session_state.history = []

for h in st.session_state.history:
    with st.chat_message(h["role"]):
        st.markdown(h["content"])

if q := st.chat_input("Ask about the data..."):
    st.session_state.history.append({"role": "user", "content": q})
    with st.chat_message("user"): st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            r = agent.ask(q)
        st.markdown(r.error or r.answer)
        with st.expander(f"steps · {len(r.tool_calls)} tool calls · {r.latency_ms} ms"):
            for c in r.tool_calls:
                st.code(f"{c['tool']}({c['input']})", language="python")
    st.session_state.history.append({"role": "assistant", "content": r.error or r.answer})
```

## ✅ CHECK
- Ask: **"how many customers do we have?"** → `800`
- Follow-up: **"and orders?"** → `4000` (memory kept context)
- Expand the steps panel — you should see `list_tables`, `describe_table`, `count_rows` calls.
