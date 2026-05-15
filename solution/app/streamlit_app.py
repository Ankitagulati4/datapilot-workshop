"""DataPilot — single-chat Streamlit app (instructor reference).

ONE tab. ONE chat. The whole product story.

Architecture:
    Streamlit UI
       |
       v
    ChatAgent (LangGraph ReAct + bind_tools)
       |
       v
    MCP servers (shopflow-sqlite + datapilot-dq + datapilot-rag)
       |
       v
    shopflow.db  +  data/rag.chroma/
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow `import solution....` from anywhere streamlit is launched
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from solution.app.charts import auto_chart
from solution.app.chat_agent import ChatAgent, filter_and_guard
from solution.app.mcp_clients import load_mcp_tools

st.set_page_config(page_title="DataPilot", page_icon="📊", layout="wide")


# ---- One-time setup --------------------------------------------------------
DQ_TOOLS = {"check_freshness", "check_nulls", "check_duplicates", "count_rows"}
RAG_TOOLS = {"search_docs", "list_docs"}


def _flatten(content) -> str:
    """MCP tool outputs come as either a plain string or a list of content
    blocks [{'type':'text','text':'...'}]. Return one flat string."""
    if isinstance(content, list):
        return "\n".join(
            (b.get("text") or "") if isinstance(b, dict) else str(b)
            for b in content
        )
    return str(content)


@st.cache_resource(show_spinner="Spawning MCP servers...")
def _bootstrap():
    """Connect to MCP servers + build the chat agent. Runs once per session."""
    client, raw_tools = load_mcp_tools()
    safe_tools = filter_and_guard(raw_tools)
    agent = ChatAgent(safe_tools)
    return client, raw_tools, safe_tools, agent


client, raw_tools, safe_tools, agent = _bootstrap()

if "messages" not in st.session_state:
    st.session_state.messages = []   # list of dicts: {role, content, turn}


# ---- Sidebar ---------------------------------------------------------------
with st.sidebar:
    st.title("📊 DataPilot")
    st.caption("AI Analytics Colleague")

    st.markdown("### 🔌 Connected MCP servers")
    by_server: dict[str, list[str]] = {}
    for t in raw_tools:
        if t.name in DQ_TOOLS:
            by_server.setdefault("datapilot-dq", []).append(t.name)
        elif t.name in RAG_TOOLS:
            by_server.setdefault("datapilot-rag", []).append(t.name)
        else:
            by_server.setdefault("shopflow-sqlite", []).append(t.name)
    for server, names in by_server.items():
        with st.expander(f"{server} · {len(names)} tools", expanded=False):
            for n in names:
                tag = "✓" if n in {t.name for t in safe_tools} else "✗"
                st.write(f"{tag} `{n}`")

    st.markdown("---")
    st.markdown("### 🩺 Health snapshot")
    if st.button("Run quick checks", width="stretch"):
        st.session_state.health = {}
        try:
            tool_map = {t.name: t for t in raw_tools}
            import asyncio
            for table in ("orders", "customers", "products"):
                if "count_rows" in tool_map:
                    res = asyncio.run(tool_map["count_rows"].ainvoke({"table": table}))
                    st.session_state.health[f"rows {table}"] = _flatten(res)
            if "check_freshness" in tool_map:
                res = asyncio.run(tool_map["check_freshness"].ainvoke({"table": "orders"}))
                st.session_state.health["freshness orders"] = _flatten(res)
        except Exception as e:
            st.session_state.health = {"error": f"{type(e).__name__}: {e}"}
    if "health" in st.session_state:
        for k, v in st.session_state.health.items():
            badge = "🟢" if v.startswith("[OK]") or "rows" in k else (
                "🟡" if v.startswith("[WARN]") else
                "🔴" if v.startswith("[FAIL]") or v.startswith("[STALE]") else "⚪"
            )
            st.caption(f"{badge} {v}")

    st.markdown("---")
    if st.button("🧹 Clear chat", width="stretch"):
        agent.reset()
        st.session_state.messages = []
        st.rerun()


# ---- Main chat area --------------------------------------------------------
st.markdown("### 💬 Ask DataPilot anything about ShopFlow")

# Render history
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("table_csv"):
            df = pd.read_csv(StringIO(msg["table_csv"]))
            fig = auto_chart(df)
            if fig is not None:
                st.plotly_chart(fig, width="stretch")
            with st.expander(f"📋 Table ({df.shape[0]} rows)"):
                st.dataframe(df, width="stretch")
        if msg.get("turn"):
            t = msg["turn"]
            st.caption(f"⚡ {t['latency_ms']} ms")
            with st.expander(f"🔍 Show steps ({len(t['tool_calls'])} tool call(s))"):
                for call in t["tool_calls"]:
                    st.markdown(f"**{call['tool']}**  `{call['input']}`")
                    st.code(call["output"], language="text")


def _maybe_extract_table(tool_calls: list[dict]) -> str | None:
    """If the last read_query returned rows, parse them back to CSV."""
    import ast
    for call in reversed(tool_calls):
        if call["tool"] != "read_query":
            continue
        text = _flatten(call["output"])
        try:
            rows = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            continue
        if (isinstance(rows, list) and rows
                and isinstance(rows[0], dict)
                and set(rows[0].keys()) >= {"type", "text"}):
            try:
                rows = ast.literal_eval(rows[0]["text"])
            except (ValueError, SyntaxError):
                continue
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return pd.DataFrame(rows).to_csv(index=False)
    return None


# Input
typed = st.chat_input("e.g., revenue last month, are orders fresh?, or what does VIP mean?")

if typed:
    prompt = typed
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("DataPilot is thinking..."):
            turn = agent.ask(prompt)
        if turn.error:
            st.error(turn.error)
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"❌ {turn.error}",
            })
        else:
            st.markdown(turn.answer or "(no answer)")
            csv = _maybe_extract_table(turn.tool_calls)
            df = pd.read_csv(StringIO(csv)) if csv else None
            if df is not None and not df.empty:
                fig = auto_chart(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
                with st.expander(f"📋 Table ({df.shape[0]} rows)"):
                    st.dataframe(df, width="stretch")

            st.caption(f"⚡ {turn.latency_ms} ms")
            with st.expander(f"🔍 Show steps ({len(turn.tool_calls)} tool call(s))"):
                for call in turn.tool_calls:
                    st.markdown(f"**{call['tool']}**  `{call['input']}`")
                    st.code(call["output"], language="text")

            st.session_state.messages.append({
                "role": "assistant",
                "content": turn.answer,
                "table_csv": csv,
                "turn": {
                    "tool_calls": turn.tool_calls,
                    "latency_ms": turn.latency_ms,
                },
            })
