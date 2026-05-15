"""Tests for the smart chart picker."""
import pandas as pd

from solution.app.charts import auto_chart


def test_returns_none_for_empty():
    assert auto_chart(pd.DataFrame()) is None


def test_returns_none_for_single_column():
    assert auto_chart(pd.DataFrame({"x": [1, 2, 3]})) is None


def test_returns_none_for_single_row():
    assert auto_chart(pd.DataFrame({"x": ["a"], "y": [1]})) is None


def test_line_chart_for_time_series():
    df = pd.DataFrame({
        "month": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "revenue": [100, 200, 300],
    })
    fig = auto_chart(df)
    assert fig is not None
    assert "line" in str(type(fig.data[0])).lower() or fig.data[0].mode == "lines+markers"


def test_bar_chart_for_categorical_top_n():
    df = pd.DataFrame({
        "category": ["A", "B", "C", "D"],
        "revenue": [100, 200, 150, 300],
    })
    fig = auto_chart(df)
    assert fig is not None


def test_returns_none_for_too_many_categories():
    df = pd.DataFrame({
        "id": [str(i) for i in range(50)],
        "v": list(range(50)),
    })
    assert auto_chart(df) is None
