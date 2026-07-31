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