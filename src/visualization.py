"""
Draws the chart chosen in analysis.choose_chart using Streamlit's built-in charts.
Kept separate from app.py so chart logic stays in one place.
"""

import streamlit as st


def render_chart(df, chart):
    """Draws a bar or line chart. Returns False if there is no chart to draw."""
    if chart["type"] == "none" or df.empty:
        return False

    x, y = chart["x"], chart["y"]
    data = df[[x, y]].copy()
    data[x] = data[x].astype(str)  # treat labels/dates as categories on the x-axis

    if chart["type"] == "bar":
        data = data.sort_values(y, ascending=False)
        st.bar_chart(data, x=x, y=y, sort=False)
    elif chart["type"] == "line":
        data = data.sort_values(x)
        st.line_chart(data, x=x, y=y)
    return True
