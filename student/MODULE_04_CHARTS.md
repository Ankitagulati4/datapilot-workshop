# Module 04 — Smart charts (10 min)

> Goal: when the answer is a small table with a date or category, draw a chart automatically. Otherwise no chart.

## 1. Create `student/app/charts.py`
```python
import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

def _is_stringy(s): return s.dtype == "object" or pd.api.types.is_string_dtype(s)

def _is_datey(s):
    if pd.api.types.is_datetime64_any_dtype(s): return True
    if _is_stringy(s) and len(s):
        try:
            pd.to_datetime(s.dropna().astype(str).head(5), errors="raise")
            return True
        except Exception: return False
    return False

def auto_chart(df: pd.DataFrame) -> Figure | None:
    if df is None or df.empty or df.shape[1] < 2 or df.shape[0] < 2: return None
    nums = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not nums: return None
    y = nums[0]
    for c in df.columns:
        if c != y and _is_datey(df[c]):
            d = df.copy(); d[c] = pd.to_datetime(d[c], errors="coerce")
            d = d.dropna(subset=[c]).sort_values(c)
            if not d.empty: return px.line(d, x=c, y=y, markers=True, title=f"{y} over {c}")
    cats = [c for c in df.columns if c != y and _is_stringy(df[c])]
    if cats and 2 <= df.shape[0] <= 25:
        return px.bar(df, x=cats[0], y=y, title=f"{y} by {cats[0]}")
    return None
```

## 2. Use it in `streamlit_app.py`
After rendering the assistant message:
```python
import pandas as pd, ast
from app.charts import auto_chart

def maybe_table(tool_calls):
    for c in reversed(tool_calls):
        if c["tool"] != "read_query": continue
        text = c["output"]
        if isinstance(text, list):  # MCP content blocks
            text = "".join(b.get("text","") for b in text if isinstance(b, dict))
        try:
            rows = ast.literal_eval(text)
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return pd.DataFrame(rows)
        except Exception: pass
    return None

df = maybe_table(r.tool_calls)
if df is not None:
    st.dataframe(df, width="stretch", hide_index=True)
    fig = auto_chart(df)
    if fig: st.plotly_chart(fig, width="stretch")
```

## ✅ CHECK
- Ask: **"top 5 product categories by revenue"** → bar chart appears.
- Ask: **"orders per month in 2025"** → line chart appears.
- Ask: **"how many customers"** → no chart (single scalar).
