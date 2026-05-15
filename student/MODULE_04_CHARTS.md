# Module 04 — Smart charts (10 min)

> Goal: when the answer is a small table with a date or category, draw a chart automatically. Otherwise no chart.

## 1. Create `student/app/charts.py`
```python
import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

# --- tiny dtype helpers ---------------------------------------------------
# True if column holds plain text (object dtype or pandas StringDtype).
def _is_stringy(s): return s.dtype == "object" or pd.api.types.is_string_dtype(s)

# True if column already IS a datetime, OR if the first 5 string values
# parse cleanly as dates (e.g. '2026-01-15' from SQLite).
# We sample only 5 rows for speed -- good enough heuristic.
def _is_datey(s):
    if pd.api.types.is_datetime64_any_dtype(s): return True
    if _is_stringy(s) and len(s):
        try:
            pd.to_datetime(s.dropna().astype(str).head(5), errors="raise")
            return True
        except Exception: return False
    return False

def auto_chart(df: pd.DataFrame) -> Figure | None:
    """Pick the right chart for `df`, or return None if a table is enough.

    Rule of thumb:
      - datetime column present       -> line chart (time series)
      - categorical + 2..25 rows      -> bar chart (top-N)
      - anything else (scalar, large) -> no chart, let the table speak
    The LLM never picks the chart type -- the *shape of the data* does.
    """
    # Skip charts for empty / single-row / single-column results.
    # 1x1 dataframe = a scalar KPI; show the number, not a chart.
    if df is None or df.empty or df.shape[1] < 2 or df.shape[0] < 2: return None

    # Need at least one numeric column for the Y axis.
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not nums: return None
    y = nums[0]   # first numeric column -> Y axis

    # --- Time series -> line chart ---------------------------------------
    for c in df.columns:
        if c != y and _is_datey(df[c]):
            d = df.copy()
            # Force-convert; rows that can't parse become NaT and get dropped.
            d[c] = pd.to_datetime(d[c], errors="coerce")
            d = d.dropna(subset=[c]).sort_values(c)
            if not d.empty: return px.line(d, x=c, y=y, markers=True, title=f"{y} over {c}")

    # --- Categorical top-N -> bar chart ----------------------------------
    # Cap at 25 rows so we don't render a 5000-bar wall of pixels.
    cats = [c for c in df.columns if c != y and _is_stringy(df[c])]
    if cats and 2 <= df.shape[0] <= 25:
        return px.bar(df, x=cats[0], y=y, title=f"{y} by {cats[0]}")

    # No suitable shape -- caller falls back to a plain dataframe view.
    return None
```

## 2. Wire it into the UI — full `student/app/streamlit_app.py`

> 💡 **Three changes vs. Module 03:**
> 1. Two new imports — `pandas`, `ast`, and `auto_chart` from `app.charts`.
> 2. A new helper `maybe_table(tool_calls)` that lifts the most recent
>    `read_query` result out of the tool trace and parses it into a DataFrame.
> 3. After rendering the assistant bubble, show the dataframe and optionally
>    a Plotly chart.
>
> Everything else (sidebar, history replay, chat loop) is identical.

Replace the **entire** contents of `student/app/streamlit_app.py` with:

```python
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

from app.mcp_clients import load_mcp_tools
from app.chat_agent import ChatAgent
from app.charts import auto_chart   # NEW in Module 04

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
```

### What changed vs. Module 03 (diff at a glance)
1. **New imports** — `ast`, `pandas as pd`, and `from app.charts import auto_chart`.
2. **New helper** — `maybe_table(tool_calls)` parses the last `read_query`
   output into a `DataFrame` (or returns `None`).
3. **New render block** — after `st.markdown(r.error or r.answer)` we call
   `maybe_table()`, then `st.dataframe()` + `auto_chart()` + `st.plotly_chart()`.
4. Sidebar, history replay, and the steps expander are byte-for-byte identical.

> ⚠️ **Restart Streamlit** after saving (Ctrl+C → re-run). `@st.cache_resource`
> caches the agent and the page module across reruns, but a brand-new helper
> like `maybe_table` only takes effect after a full process restart.

## ✅ CHECK
- Ask: **"top 5 product categories by revenue"** → bar chart appears.
- Ask: **"orders per month in 2025"** → line chart appears.
- Ask: **"how many customers"** → no chart (single scalar).
