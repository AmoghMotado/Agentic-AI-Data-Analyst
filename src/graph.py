"""
The analyst agent, built as a LangGraph workflow.

LangGraph pieces:
- State: a dictionary shared by all steps (AgentState below).
- Nodes: plain functions; each reads the state and returns the fields it changes.
- Edges: which node runs next. Conditional edges choose based on the state,
  which is how we branch (valid/invalid SQL) and loop (retry on errors).

Flow:
START -> get_schema -> generate_sql -> validate_sql -> execute_sql
      -> analyze_result -> generate_insight -> END
with branches for ambiguous / unsupported questions and a limited retry loop
back to generate_sql when validation or execution fails.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src import sql_generator
from src.analysis import analyze, choose_chart, facts_to_text, to_dataframe
from src.config import MAX_RETRIES, get_api_key
from src.database import database_exists
from src.schema import get_schema_text
from src.sql_validator import clean_sql, validate_sql
from src.tools import execute_sql


class AgentState(TypedDict, total=False):
    question: str        # the user's question (needed by every LLM step)
    schema: str          # schema text that grounds the LLM in real tables/columns
    status: str          # answerable | ambiguous | unsupported | error | done
    sql: str             # latest generated SQL (shown in the UI)
    is_valid: bool       # validator result, drives the valid/invalid branch
    error: str           # latest validation/execution error (sent back to the LLM on retry)
    retry_count: int     # number of correction attempts so far (prevents infinite loops)
    columns: list        # result column names from the database tool
    rows: list           # result rows from the database tool
    truncated: bool      # True if the result had more rows than MAX_ROWS
    analysis: dict       # facts computed with Pandas
    chart: dict          # chart choice: {"type": bar|line|none, "x": ..., "y": ...}
    final_answer: str    # message shown to the user
    steps: list          # names of nodes that ran (for debug mode only)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def get_schema_node(state):
    return {"schema": get_schema_text(), "steps": state["steps"] + ["get_schema"]}


def generate_sql_node(state):
    is_retry = bool(state.get("error"))
    retry_count = state.get("retry_count", 0) + (1 if is_retry else 0)
    steps = state["steps"] + ["generate_sql" + (f" (correction {retry_count})" if is_retry else "")]
    try:
        response = sql_generator.generate_sql(
            state["question"], state["schema"],
            previous_sql=state.get("sql", ""), error=state.get("error", ""),
        )
    except Exception as exc:
        return {"status": "error", "final_answer": f"The language model request failed: {exc}", "steps": steps}

    return {
        "status": response.status,
        "sql": clean_sql(response.sql),
        "final_answer": response.message,
        "retry_count": retry_count,
        "error": "",
        "steps": steps,
    }


def validate_sql_node(state):
    is_valid, reason = validate_sql(state["sql"])
    return {"is_valid": is_valid, "error": reason, "steps": state["steps"] + ["validate_sql"]}


def execute_sql_node(state):
    # Tool calling: the graph invokes the LangChain database tool
    result = execute_sql.invoke({"query": state["sql"]})
    return {
        "columns": result["columns"],
        "rows": result["rows"],
        "truncated": result["truncated"],
        "error": result["error"],
        "steps": state["steps"] + ["execute_sql"],
    }


def analyze_result_node(state):
    df = to_dataframe(state["columns"], state["rows"])
    chart = choose_chart(df)
    return {"analysis": analyze(df, chart), "chart": chart, "steps": state["steps"] + ["analyze_result"]}


def generate_insight_node(state):
    steps = state["steps"] + ["generate_insight"]
    facts = state["analysis"]
    if facts["row_count"] == 0:
        return {"status": "done", "steps": steps,
                "final_answer": "The query ran successfully but returned no matching data."}

    df = to_dataframe(state["columns"], state["rows"])
    try:
        insight = sql_generator.generate_insight(
            state["question"], state["sql"], df.head(20).to_string(index=False), facts_to_text(facts)
        )
    except Exception:
        # The data is still correct; fall back to a plain summary instead of failing
        insight = "Here is the result of your question (the AI insight could not be generated)."
    return {"status": "done", "final_answer": insight, "steps": steps}


def respond_error_node(state):
    message = (
        f"I couldn't produce a working query after {MAX_RETRIES} correction attempts. "
        f"Last error: {state.get('error')}. Try rephrasing the question."
    )
    return {"status": "error", "final_answer": message, "steps": state["steps"] + ["respond_error"]}


# ---------------------------------------------------------------------------
# Conditional edges (routing functions)
# ---------------------------------------------------------------------------

def route_after_generate(state):
    if state["status"] == "answerable" and state.get("sql"):
        return "validate_sql"
    # ambiguous / unsupported / LLM error: the message is already in final_answer
    return END


def route_after_validate(state):
    if state["is_valid"]:
        return "execute_sql"
    return "generate_sql" if state["retry_count"] < MAX_RETRIES else "respond_error"


def route_after_execute(state):
    if not state["error"]:
        return "analyze_result"
    return "generate_sql" if state["retry_count"] < MAX_RETRIES else "respond_error"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("get_schema", get_schema_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("analyze_result", analyze_result_node)
    graph.add_node("generate_insight", generate_insight_node)
    graph.add_node("respond_error", respond_error_node)

    graph.add_edge(START, "get_schema")
    graph.add_edge("get_schema", "generate_sql")
    graph.add_conditional_edges("generate_sql", route_after_generate, ["validate_sql", END])
    graph.add_conditional_edges("validate_sql", route_after_validate,
                                ["execute_sql", "generate_sql", "respond_error"])
    graph.add_conditional_edges("execute_sql", route_after_execute,
                                ["analyze_result", "generate_sql", "respond_error"])
    graph.add_edge("analyze_result", "generate_insight")
    graph.add_edge("generate_insight", END)
    graph.add_edge("respond_error", END)

    return graph.compile()


_app = None


def run_analysis(question):
    """Entry point used by the UI. Always returns a state dict; never raises."""
    global _app
    question = (question or "").strip()
    if not question:
        return {"status": "error", "final_answer": "Please type a question.", "steps": []}
    if not get_api_key():
        return {"status": "error", "steps": [],
                "final_answer": "OpenAI API key is missing. Add OPENAI_API_KEY to your .env file and restart."}
    if not database_exists():
        return {"status": "error", "steps": [],
                "final_answer": "Database not found. Run: python scripts/create_database.py"}

    if _app is None:
        _app = build_graph()
    try:
        return _app.invoke({"question": question, "retry_count": 0, "steps": []})
    except Exception as exc:
        return {"status": "error", "final_answer": f"Something went wrong: {exc}", "steps": []}


if __name__ == "__main__":
    # Quick terminal test:  python -m src.graph "Which region generated the most revenue?"
    import sys

    q = " ".join(sys.argv[1:]) or "Which region generated the most revenue?"
    result = run_analysis(q)
    print("STEPS :", " -> ".join(result.get("steps", [])))
    print("SQL   :", result.get("sql", ""))
    print("ROWS  :", result.get("rows", [])[:10])
    print("ANSWER:", result.get("final_answer"))
