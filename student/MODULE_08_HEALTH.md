# Module 08 — Health snapshot in the sidebar (15 min)

> Goal: a "Run quick checks" button that calls your DQ tools and shows a red/green snapshot. Build instinct: this is what real teams ship.

## Add to `student/app/streamlit_app.py` (sidebar)

```python
import asyncio

def _flatten(c):
    if isinstance(c, list):
        return "\n".join(b.get("text","") if isinstance(b, dict) else str(b) for b in c)
    return str(c)

with st.sidebar:
    st.divider()
    st.subheader("Health snapshot")
    if "health" not in st.session_state:
        st.session_state.health = {}
    if st.button("Run quick checks", width="stretch"):
        st.session_state.health = {}
        tmap = {t.name: t for t in tools}
        try:
            for tbl in ("orders","customers","products"):
                if "count_rows" in tmap:
                    st.session_state.health[f"rows {tbl}"] = _flatten(
                        asyncio.run(tmap["count_rows"].ainvoke({"table": tbl})))
            if "check_freshness" in tmap:
                st.session_state.health["freshness orders"] = _flatten(
                    asyncio.run(tmap["check_freshness"].ainvoke({"table":"orders"})))
        except Exception as e:
            st.session_state.health["error"] = f"{type(e).__name__}: {e}"
    for k, v in st.session_state.health.items():
        if "STALE" in v or "error" in k.lower(): st.error(f"{k}: {v}")
        else: st.success(f"{k}: {v}")
```

## ✅ CHECK
- Click **Run quick checks**.
- See 4 lines — 3 green row-counts and one freshness badge (likely STALE for the synthetic data — that's correct!).
- The chat is unaffected; the user can run checks any time.
