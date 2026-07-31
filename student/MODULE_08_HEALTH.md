# Module 08 — Health snapshot in the sidebar (15 min)

> Goal: a "Run quick checks" button that calls your DQ tools and shows a red/green snapshot. Build instinct: this is what real teams ship.

## Add to `student/app/streamlit_app.py` (sidebar)

First, make sure `run_sync` is imported at the top of the file — add it to the
**existing** `mcp_clients` import line:

```python
from app.mcp_clients import load_mcp_tools, run_sync
```

Then add this helper + sidebar block:

```python
def _flatten(c):
    """MCP tools may return either a plain string OR a list of content blocks
    like [{'type':'text','text':'...'}]. Collapse both shapes into one string
    so the UI can render it uniformly."""
    if isinstance(c, list):
        return "\n".join(b.get("text","") if isinstance(b, dict) else str(b) for b in c)
    return str(c)

with st.sidebar:
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
```

## ✅ CHECK
- Click **Run quick checks**.
- See 4 lines — 3 green row-counts and one freshness badge (likely STALE for the synthetic data — that's correct!).
- It should feel **near-instant** (~30 ms total). If it takes several seconds,
  you're probably calling the tools with `asyncio.run(...)` instead of
  `run_sync(...)` — that spawns a fresh event loop per call and can't reuse the
  live MCP session. Use `run_sync`.
- The chat is unaffected; the user can run checks any time.
