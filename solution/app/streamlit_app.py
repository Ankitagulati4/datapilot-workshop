"""DataPilot — single-chat Streamlit app (instructor reference).

ONE tab. ONE chat. The whole product story.

Architecture:
    Streamlit UI
       |
       v
    ChatAgent (LangChain agent + bind_tools)
       |
       v
    MCP servers (sqlite + datapilot-dq)  --> the database
"""
from __future__ import annotations

import json
import os
import sys
from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow `import solution....` from anywhere streamlit is launched
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from solution.app.charts import auto_chart
from solution.app.chat_agent import ChatAgent, filter_and_guard
from solution.app.cost import crude_token_count, estimate_usd
from solution.app.mcp_clients import load_mcp_tools
from solution.app import storage

st.set_page_config(page_title="DataPilot", page_icon="📊", layout="wide")


# ---- One-time setup --------------------------------------------------------
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
if "saved" not in st.session_state:
    st.session_state.saved = storage.load()
if "spent" not in st.session_state:
    st.session_state.spent = {"input": 0, "output": 0, "usd": 0.0, "turns": 0}


# ---- Sidebar ---------------------------------------------------------------
with st.sidebar:
    st.title("📊 DataPilot")
    st.caption("AI Analytics Colleague")

    st.markdown("### 🔌 Connected MCP servers")
    by_server: dict[str, list[str]] = {}
    for t in raw_tools:
        # langchain-mcp-adapters does not always set metadata.server reliably,
        # so we infer by tool-name prefix that we know from mcp.json.
        if t.name in {"check_freshness", "check_nulls", "check_duplicates", "count_rows"}:
            by_server.setdefault("datapilot-dq", []).append(t.name)
        else:
            by_server.setdefault("shopflow-sqlite", []).append(t.name)
    for server, names in by_server.items():
        with st.expander(f"{server} · {len(names)} tools", expanded=False):
            for n in names:
                tag = "✓" if n in {t.name for t in safe_tools} else "✗"
                st.write(f"{tag} `{n}`")

    st.markdown("---")
    st.markdown("### ★ Saved questions")
    if not st.session_state.saved:
        st.caption("Save useful turns with the ★ button to replay them later.")
    for q in list(st.session_state.saved):
        cols = st.columns([6, 1])
        if cols[0].button(q, key=f"saved_{q}", width="stretch"):
            st.session_state.replay_q = q
            st.rerun()
        if cols[1].button("✕", key=f"del_{q}"):
            st.session_state.saved = storage.remove(q)
            st.rerun()

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
    s = st.session_state.spent
    st.caption(f"💰 Today: {s['turns']} turns · {s['input']+s['output']} tok · ${s['usd']:.4f}")
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
            cols = st.columns([1, 1, 6])
            with cols[0]:
                if st.button("★ Save", key=f"save_{i}"):
                    if msg.get("question"):
                        st.session_state.saved = storage.add(msg["question"])
                        st.rerun()
            with cols[1]:
                cost = estimate_usd(t["input_tokens"], t["output_tokens"])
                st.caption(f"⚡ {t['latency_ms']} ms · ${cost:.4f}")
            with st.expander(f"🔍 Show steps ({len(t['tool_calls'])} tool call(s))"):
                for call in t["tool_calls"]:
                    st.markdown(f"**{call['tool']}**  `{call['input']}`")
                    st.code(call["output"], language="text")


def _maybe_extract_table(tool_calls: list[dict]) -> str | None:
    """If the last read_query returned rows, parse them back to CSV.

    sqlite-mcp returns `[{'col': v, ...}, {...}]` as a Python literal.
    With newer langchain-mcp-adapters that literal is wrapped in a
    content block: `[{'type':'text','text': "[{...}, ...]", 'id': '...'}]`.
    Peel both shapes.
    """
    import ast
    for call in reversed(tool_calls):
        if call["tool"] != "read_query":
            continue
        text = _flatten(call["output"])
        try:
            rows = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            continue
        # Unwrap content-block dicts if needed
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
prompt = st.session_state.pop("replay_q", None)
typed = st.chat_input("e.g., revenue last month, or are orders fresh?")
if typed:
    prompt = typed

if prompt:
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

            in_tok = crude_token_count(prompt)
            out_tok = crude_token_count(turn.answer)
            cost = estimate_usd(in_tok, out_tok)
            st.session_state.spent["input"] += in_tok
            st.session_state.spent["output"] += out_tok
            st.session_state.spent["usd"] += cost
            st.session_state.spent["turns"] += 1

            cols = st.columns([1, 1, 6])
            with cols[0]:
                if st.button("★ Save", key=f"save_new_{len(st.session_state.messages)}"):
                    st.session_state.saved = storage.add(prompt)
                    st.rerun()
            with cols[1]:
                st.caption(f"⚡ {turn.latency_ms} ms · ${cost:.4f}")

            with st.expander(f"🔍 Show steps ({len(turn.tool_calls)} tool call(s))"):
                for call in turn.tool_calls:
                    st.markdown(f"**{call['tool']}**  `{call['input']}`")
                    st.code(call["output"], language="text")

            st.session_state.messages.append({
                "role": "assistant",
                "content": turn.answer,
                "table_csv": csv,
                "question": prompt,
                "turn": {
                    "tool_calls": turn.tool_calls,
                    "latency_ms": turn.latency_ms,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                },
            })
