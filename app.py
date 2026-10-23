"""
Streamlit UI. Run with:  streamlit run app.py

The UI only collects the question (and an optional uploaded database) and
displays results. All the thinking happens in src/graph.py (the LangGraph agent).
"""

import streamlit as st

from src.analysis import to_dataframe
from src.config import OPENAI_MODEL, get_api_key
from src.database import database_exists
from src.graph import run_analysis
from src.schema import get_dataset_info
from src.uploads import UploadError, save_upload
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
def load_dataset_info(db_path):
    return get_dataset_info(db_path or None)


def prepare_upload(files):
    """files: list of (name, bytes). save_upload reuses the saved database if it already exists."""
    return str(save_upload(files))


def format_number(value):
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    return f"{int(value):,}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📁 Dataset")

    uploaded = st.file_uploader(
        "Upload your own data (optional)",
        type=["db", "sqlite", "sqlite3", "csv"],
        accept_multiple_files=True,
        help="One SQLite database file, or one or more CSV files (each CSV becomes a table). "
             "Remove the files to go back to the sample data.",
    )

    # Which database the agent analyses: the upload if there is one, else the sample
    db_path, db_label = "", "NovaMart sales sample (SQLite)"
    if uploaded:
        try:
            db_path = prepare_upload([(f.name, f.getvalue()) for f in uploaded])
            db_label = ", ".join(f.name for f in uploaded)
        except UploadError as exc:
            st.error(str(exc))
            db_path, db_label = None, None

    # A different database makes the previous answer stale
    if st.session_state.get("active_db") != db_path:
        st.session_state.active_db = db_path
        st.session_state.pop("result", None)

    if db_path is None:
        st.info("Fix the upload above to continue.")
    elif database_exists(db_path or None):
        info = load_dataset_info(db_path)
        lines = [f"**{db_label}**"]
        lines += [f"{table}: {count:,} rows" for table, count in info["tables"].items()]
        if "date_range" in info:
            lines.append(f"Dates: {info['date_range']}")
        st.markdown("  \n".join(lines))
    else:
        st.error("Database not found. Run `python scripts/create_database.py`.")

    if not db_path:
        st.header("💡 Example questions")
        for example in EXAMPLE_QUESTIONS:
            if st.button(example, width="stretch"):
                st.session_state.question = example
                st.session_state.run = True
    else:
        st.caption("Ask any question about the tables listed above.")

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
        placeholder=("e.g. Which category has the highest total?" if db_path
                     else "e.g. Which region generated the most revenue?"),
    )
    submitted = st.form_submit_button("Ask", type="primary")

if submitted or st.session_state.pop("run", False):
    if db_path is None:
        st.session_state.result = {"status": "error", "steps": [],
                                   "final_answer": "The uploaded file can't be used. See the message in the sidebar."}
    else:
        with st.spinner("Analyzing: generating SQL, running it, and reading the result..."):
            st.session_state.result = run_analysis(st.session_state.question, db_path or None)

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
