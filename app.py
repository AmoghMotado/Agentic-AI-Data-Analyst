"""
Streamlit UI. Run with:  streamlit run app.py

The UI only collects the question and displays results.
All the thinking happens in src/graph.py (the LangGraph agent).
"""

import streamlit as st

from src.analysis import to_dataframe
from src.config import OPENAI_MODEL, get_api_key
from src.database import database_exists
from src.graph import run_analysis
from src.schema import get_dataset_info
from src.visualization import render_chart

EXAMPLE_QUESTIONS = [
    "Which region generated the most revenue?",
    "What are the top 5 products by revenue?",
    "Show monthly revenue in 2025.",
    "Which category performed best?",
    "How many orders were placed?",
    "What was the average order value?",
    "Which products have declining sales from 2024 to 2025?",
]

st.set_page_config(page_title="Agentic AI Data Analyst", page_icon="📊", layout="wide")


@st.cache_data
def load_dataset_info():
    return get_dataset_info()


def format_number(value):
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📁 Dataset")
    if database_exists():
        info = load_dataset_info()
        st.markdown(
            f"**NovaMart sales (SQLite)**  \n"
            f"Customers: {info['customers']}  \n"
            f"Products: {info['products']}  \n"
            f"Orders: {info['orders']}  \n"
            f"Order items: {info['order_items']}  \n"
            f"Dates: {info['date_range']}"
        )
    else:
        st.error("Database not found. Run `python scripts/create_database.py`.")

    st.header("💡 Example questions")
    for example in EXAMPLE_QUESTIONS:
        if st.button(example, width="stretch"):
            st.session_state.question = example
            st.session_state.run = True

    st.divider()
    if st.button("🔄 Reset", width="stretch"):
        st.session_state.clear()
        st.rerun()
    debug = st.toggle("Debug mode", help="Show the workflow steps the agent ran")
    st.caption(f"Model: {OPENAI_MODEL}")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("📊 Agentic AI Data Analyst")
st.write("Ask questions about your business data using natural language.")

if not get_api_key():
    st.warning("OPENAI_API_KEY is not set. Copy `.env.example` to `.env`, add your key, and restart.")

with st.form("question_form"):
    question = st.text_input(
        "Your question",
        key="question",
        placeholder="e.g. Which region generated the most revenue?",
    )
    submitted = st.form_submit_button("Ask", type="primary")

if submitted or st.session_state.pop("run", False):
    with st.spinner("Analyzing: generating SQL, running it, and reading the result..."):
        st.session_state.result = run_analysis(st.session_state.question)

result = st.session_state.get("result")
if result:
    status = result.get("status")

    if status == "ambiguous":
        st.info(f"🤔 {result['final_answer']}")
    elif status == "unsupported":
        st.warning(f"🚫 {result['final_answer'] or 'I don’t have enough data in the current database to answer that question.'}")
    elif status == "error":
        st.error(result["final_answer"])
        if result.get("sql"):
            with st.expander("Last generated SQL"):
                st.code(result["sql"], language="sql", wrap_lines=True)
    elif status == "done":
        df = to_dataframe(result["columns"], result["rows"])

        st.subheader("🧠 Generated SQL")
        st.code(result["sql"], language="sql", wrap_lines=True)

        st.subheader("📋 Query result")
        facts = result.get("analysis", {})
        if "single_value" in facts:
            single = facts["single_value"]
            st.metric(single["column"].replace("_", " ").title(), format_number(single["value"]))
        else:
            st.dataframe(df, width="stretch", hide_index=True)
        if result.get("truncated"):
            st.caption("Showing the first rows only.")

        chart = result.get("chart", {"type": "none"})
        if chart["type"] != "none":
            st.subheader("📈 Visualization")
            try:
                render_chart(df, chart)
            except Exception as exc:
                st.caption(f"Chart could not be drawn: {exc}")

        st.subheader("💬 AI insight")
        st.success(result["final_answer"])

    if debug:
        with st.expander("🔍 Debug: workflow steps", expanded=True):
            st.write(" → ".join(result.get("steps", [])))
            st.json({
                "status": status,
                "retry_count": result.get("retry_count", 0),
                "chart": result.get("chart"),
                "pandas_facts": result.get("analysis"),
            })
