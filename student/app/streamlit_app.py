"""DataPilot — Module 04: chat agent + auto-charts."""

# --- import path shim -------------------------------------------------------
# Streamlit launches this file from the repo root, so `from app.foo import ...`
# would fail with ModuleNotFoundError. Add this file's parent (student/) to
# sys.path so `app` is an importable top-level package.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# ---------------------------------------------------------------------------

import ast                          # safe parser for the SQL tool's row output
import pandas as pd
import streamlit as st

from app.mcp_clients import load_mcp_tools, run_sync
from app.chat_agent import ChatAgent
from app.charts import auto_chart   # NEW in Module 04

def _flatten(c):
    """MCP tools may return either a plain string OR a list of content blocks
    like [{'type':'text','text':'...'}]. Collapse both shapes into one string
    so the UI can render it uniformly."""
    if isinstance(c, list):
        return "\n".join(b.get("text","") if isinstance(b, dict) else str(b) for b in c)
    return str(c)

# --- Page chrome ------------------------------------------------------------
st.set_page_config(page_title="DataPilot (student)", page_icon="🛠️", layout="wide")
st.title("🛠️ DataPilot — let's build it")
st.caption("Module 04: chat agent with auto-charts.")

# --- One-time setup: spawn MCP servers, build the agent --------------------
# st.cache_resource keeps ONE shared instance per Streamlit session, so we
# don't respawn subprocesses or rebuild the LangGraph on every UI rerun.
@st.cache_resource(show_spinner="Spawning MCP servers...")
def get_tools_and_agent():
    _, cfg = load_mcp_tools()       # cfg = {server: spec} for the sidebar
    agent = ChatAgent()             # agent owns the (filtered) tool list
    return agent.tools, cfg, agent  # show what the AGENT actually sees

tools, cfg, agent = get_tools_and_agent()

# --- Sidebar: MCP server + tool list ---------------------------------------
with st.sidebar:
    st.header("MCP servers")
    for name in cfg:
        st.success(f"● {name}")
    with st.expander(f"Tools ({len(tools)})"):
        for t in tools:
            st.caption(f"`{t.name}` — {t.description[:60]}")

    st.divider()
    st.subheader("Health snapshot")

    # Persist results across Streamlit reruns so the snapshot stays visible
    # after the user types in the chat box (which causes a full rerun).
    if "health" not in st.session_state:
        st.session_state.health = {}

    if st.button("Run quick checks", width="stretch"):
        # Reset previous results -- this is a fresh snapshot.
        st.session_state.health = {}

        # Convert the flat tools list into a name->tool lookup so we can
        # invoke specific MCP tools directly (bypassing the LLM for speed).
        tmap = {t.name: t for t in tools}
        try:
            # Row counts for our three core tables.
            for tbl in ("orders","customers","products"):
                if "count_rows" in tmap:
                    # Drive the call on the SAME persistent loop that owns the
                    # live MCP sessions (run_sync). Using asyncio.run here would
                    # spin up a NEW loop per call and can't reuse the open
                    # session -> every check would be slow. run_sync = ~20 ms.
                    st.session_state.health[f"rows {tbl}"] = _flatten(
                        run_sync(tmap["count_rows"].ainvoke({"table": tbl})))
            # Freshness check for the orders table.
            if "check_freshness" in tmap:
                st.session_state.health["freshness orders"] = _flatten(
                    run_sync(tmap["check_freshness"].ainvoke({"table":"orders"})))
        except Exception as e:
            # Capture failures (server down, missing tool, etc.) into the snapshot
            # itself so the user sees them next to the green rows.
            st.session_state.health["error"] = f"{type(e).__name__}: {e}"

    # Render the snapshot every rerun. Red on STALE / error, green otherwise.
    for k, v in st.session_state.health.items():
        if "STALE" in v or "error" in k.lower(): st.error(f"{k}: {v}")
        else: st.success(f"{k}: {v}")


# --- NEW in Module 04: pull a DataFrame out of the tool trace --------------
def maybe_table(tool_calls):
    """Walk the tool-call trace in reverse and extract the most recent
    read_query result as a DataFrame. Return None if no usable table.

    We scan in reverse so that if the agent ran several queries this turn,
    we show the LAST one -- which is almost always the final answer.
    """
    for c in reversed(tool_calls):
        # We only care about the SQL tool's output -- the others return strings.
        if c["tool"] != "read_query":
            continue
        text = c["output"]
        # MCP tools can return a list of content blocks ([{type,text}, ...])
        # -- flatten them into one string before parsing.
        if isinstance(text, list):
            text = "".join(b.get("text", "") for b in text if isinstance(b, dict))
        try:
            # mcp-server-sqlite returns rows as a Python-literal string like
            # "[{'id': 1, 'name': 'A'}, ...]". ast.literal_eval safely parses
            # it (unlike eval, it only accepts literals -- no code execution).
            rows = ast.literal_eval(text)
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return pd.DataFrame(rows)
        except Exception:
            # Output wasn't parseable rows (e.g. an error message). Skip it.
            pass
    return None


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

        # --- NEW in Module 04: table + auto-chart --------------------------
        # Try to lift a table out of this turn's tool calls.
        df = maybe_table(r.tool_calls)
        if df is not None:
            # Always show the raw rows so the user can verify the claim.
            st.dataframe(df, width="stretch", hide_index=True)
            # Then optionally overlay a chart IF the data shape warrants one.
            # auto_chart() returns None for scalars / huge tables -> no chart.
            fig = auto_chart(df)
            if fig:
                st.plotly_chart(fig, width="stretch")

        # Collapsible trace: how many tools were called, latency, what they ran.
        with st.expander(f"steps · {len(r.tool_calls)} tool calls · {r.latency_ms} ms"):
            for c in r.tool_calls:
                st.code(f"{c['tool']}({c['input']})", language="python")
                if c.get("output"):
                    st.code(str(c["output"])[:600], language="text")

    # 3. Persist for the next rerun.
    st.session_state.history.append({"role": "assistant", "content": r.error or r.answer})