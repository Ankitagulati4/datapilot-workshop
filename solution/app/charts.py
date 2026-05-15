"""Smart chart picker.

Returns a Plotly figure ONLY when the result is chart-worthy:
  * line  — when there is a date/time column + a numeric column
  * bar   — when there are 2-25 categorical rows + a numeric column

Otherwise returns None and the UI just shows the table. No chart for a
single-row scalar answer like "total revenue: $1.08M".
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure


def _is_stringy(s: pd.Series) -> bool:
    return s.dtype == "object" or pd.api.types.is_string_dtype(s)


def _is_datey(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if _is_stringy(s) and len(s) > 0:
        sample = s.dropna().astype(str).head(5)
        try:
            pd.to_datetime(sample, errors="raise")
            return True
        except (ValueError, TypeError):
            return False
    return False


def auto_chart(df: pd.DataFrame) -> Figure | None:
    if df is None or df.empty or df.shape[1] < 2 or df.shape[0] < 2:
        return None

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return None
    y = numeric_cols[0]

    # Time series → line
    for c in df.columns:
        if c != y and _is_datey(df[c]):
            d = df.copy()
            d[c] = pd.to_datetime(d[c], errors="coerce")
            d = d.dropna(subset=[c]).sort_values(c)
            if d.empty:
                continue
            return px.line(d, x=c, y=y, markers=True, title=f"{y} over {c}")

    # Categorical top-N → bar
    cat_cols = [c for c in df.columns if c != y and _is_stringy(df[c])]
    if cat_cols and 2 <= df.shape[0] <= 25:
        x = cat_cols[0]
        return px.bar(df, x=x, y=y, title=f"{y} by {x}")

    return None
