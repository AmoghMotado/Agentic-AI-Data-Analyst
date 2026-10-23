"""
The database tool.

@tool turns a normal Python function into a LangChain Tool: it gets a name,
a description and an input schema. The LangGraph workflow calls this tool
instead of touching the database directly, and the UI never touches the
database at all.

The tool validates the SQL again before running it, so it is safe even if
someone calls it outside the graph.
"""

from langchain_core.tools import tool

from src.database import run_query
from src.sql_validator import clean_sql, validate_sql


@tool
def execute_sql(query: str, db_path: str = "") -> dict:
    """Run one read-only SQLite SELECT query on the active database and return the rows.
    db_path is the database file; leave it empty to use the built-in sample database."""
    is_valid, reason = validate_sql(query)
    if not is_valid:
        return {"ok": False, "error": f"Blocked: {reason}", "columns": [], "rows": [], "truncated": False}
    try:
        columns, rows, truncated = run_query(clean_sql(query), db_path=db_path or None)
        return {"ok": True, "error": "", "columns": columns, "rows": rows, "truncated": truncated}
    except Exception as exc:  # e.g. "no such column: revenue"
        return {"ok": False, "error": str(exc).split("\n")[0], "columns": [], "rows": [], "truncated": False}
