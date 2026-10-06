"""
Pandas analysis of the query result.

SQL already did the heavy aggregation (SUM, GROUP BY). Pandas adds what is
awkward in SQL and useful for the insight: highest/lowest, total, share of
total, change over time. These facts are passed to the LLM so the insight
uses real computed numbers instead of the LLM doing arithmetic.

This module also decides which chart (if any) fits the result.
"""

import re

import pandas as pd

DATE_PATTERN = re.compile(r"^\d{4}(-\d{2})?(-\d{2})?$")  # 2025, 2025-03, 2025-03-14


def to_dataframe(columns, rows):
    df = pd.DataFrame(rows, columns=columns)
    # SQLite can return numbers as text in some expressions; convert where possible
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().all() and len(df) > 0:
                df[col] = converted
    return df


def _numeric_columns(df):
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not c.lower().endswith("_id")]


def _is_time_column(df, col):
    if pd.api.types.is_numeric_dtype(df[col]):
        # A number column counts as time only if it is clearly a year, e.g. 2024, 2025
        return "year" in col.lower() and df[col].between(1900, 2100).all()
    return df[col].astype(str).str.match(DATE_PATTERN).all()


def _label_columns(df):
    return [c for c in df.columns if c not in _numeric_columns(df)]


def choose_chart(df):
    """
    Rule-based chart choice:
      time column + number       -> line chart
      one label column + number  -> bar chart (2 to 30 rows)
      anything else              -> no chart (single value, wide tables, ...)
    Returns {"type": "line"|"bar"|"none", "x": column, "y": column}.
    """
    numeric = _numeric_columns(df)
    if len(df) < 2 or not numeric:
        return {"type": "none", "x": None, "y": None}

    time_cols = [c for c in df.columns if _is_time_column(df, c)]
    if time_cols:
        y = next((c for c in numeric if c not in time_cols), None)
        if y:
            return {"type": "line", "x": time_cols[0], "y": y}

    labels = _label_columns(df)
    if labels and len(df) <= 30:
        return {"type": "bar", "x": labels[0], "y": numeric[0]}

    return {"type": "none", "x": None, "y": None}


def analyze(df, chart):
    """Returns a dict of simple facts about the result."""
    facts = {"row_count": int(len(df))}
    if df.empty:
        return facts

    numeric = _numeric_columns(df)

    # Single value, e.g. "total revenue" or "number of orders"
    if len(df) == 1 and len(df.columns) == 1 and numeric:
        facts["single_value"] = {"column": df.columns[0], "value": float(df.iloc[0, 0])}
        return facts

    x, y = chart["x"], chart["y"]

    if chart["type"] == "bar":
        ranked = df.sort_values(y, ascending=False)
        total = float(df[y].sum())
        top, bottom = ranked.iloc[0], ranked.iloc[-1]
        facts["metric"] = y
        facts["highest"] = {x: str(top[x]), y: float(top[y])}
        facts["lowest"] = {x: str(bottom[x]), y: float(bottom[y])}
        facts["total"] = round(total, 2)
        facts["average"] = round(float(df[y].mean()), 2)
        if total > 0 and (df[y] >= 0).all():
            facts["highest_share_percent"] = round(float(top[y]) / total * 100, 1)

    elif chart["type"] == "line":
        series = df.sort_values(x)
        first, last = series.iloc[0], series.iloc[-1]
        peak = series.loc[series[y].idxmax()]
        facts["metric"] = y
        facts["period"] = f"{first[x]} to {last[x]}"
        facts["first_value"] = float(first[y])
        facts["last_value"] = float(last[y])
        facts["peak"] = {x: str(peak[x]), y: float(peak[y])}
        facts["total"] = round(float(series[y].sum()), 2)
        if first[y]:
            facts["change_percent_first_to_last"] = round((last[y] - first[y]) / first[y] * 100, 1)

    else:
        # No chart: still give basic statistics for numeric columns
        for col in numeric[:3]:
            facts[f"{col}_stats"] = {
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": round(float(df[col].mean()), 2),
            }
    return facts


def facts_to_text(facts):
    return "\n".join(f"- {key}: {value}" for key, value in facts.items())
