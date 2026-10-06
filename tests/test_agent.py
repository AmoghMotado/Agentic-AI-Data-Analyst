"""
Agent workflow tests WITHOUT calling OpenAI.

We replace the two LLM functions with fake ones ("mocking"), so we can test
the LangGraph routing, retry loop and safety checks for free and offline.
"""

import pytest

from src import graph, sql_generator
from src.sql_generator import SQLResponse


@pytest.fixture(autouse=True)
def fake_setup(monkeypatch):
    monkeypatch.setattr(graph, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(sql_generator, "generate_insight", lambda *args: "Fake insight.")
    graph._app = None


def use_fake_llm(monkeypatch, responses):
    """Each call to generate_sql returns the next response in the list."""
    calls = []

    def fake_generate_sql(question, schema, previous_sql="", error=""):
        calls.append(error)
        return responses[len(calls) - 1]

    monkeypatch.setattr(sql_generator, "generate_sql", fake_generate_sql)
    return calls


def test_normal_question(monkeypatch):
    use_fake_llm(monkeypatch, [SQLResponse(
        status="answerable", message="",
        sql="SELECT c.region, SUM(oi.quantity * oi.unit_price) AS revenue FROM orders o "
            "JOIN customers c ON o.customer_id = c.customer_id "
            "JOIN order_items oi ON o.order_id = oi.order_id GROUP BY c.region ORDER BY revenue DESC",
    )])
    result = graph.run_analysis("Which region generated the most revenue?")
    assert result["status"] == "done"
    assert result["chart"]["type"] == "bar"
    assert result["analysis"]["highest"]["region"] == "West"
    assert result["final_answer"] == "Fake insight."


def test_ambiguous_question(monkeypatch):
    use_fake_llm(monkeypatch, [SQLResponse(status="ambiguous", sql="", message="Do you mean revenue or orders?")])
    result = graph.run_analysis("Show performance.")
    assert result["status"] == "ambiguous"
    assert "execute_sql" not in result["steps"]


def test_unsupported_question(monkeypatch):
    use_fake_llm(monkeypatch, [SQLResponse(status="unsupported", sql="", message="No weather data.")])
    result = graph.run_analysis("What is the weather today?")
    assert result["status"] == "unsupported"


def test_sql_error_recovery(monkeypatch):
    calls = use_fake_llm(monkeypatch, [
        SQLResponse(status="answerable", sql="SELECT revenue FROM orders", message=""),
        SQLResponse(status="answerable", sql="SELECT COUNT(*) AS total_orders FROM orders", message=""),
    ])
    result = graph.run_analysis("How many orders?")
    assert result["status"] == "done"
    assert result["retry_count"] == 1
    assert "no such column" in calls[1]  # the error was sent back to the LLM


def test_unsafe_sql_is_never_executed_and_retries_stop(monkeypatch):
    bad = SQLResponse(status="answerable", sql="DROP TABLE orders", message="")
    calls = use_fake_llm(monkeypatch, [bad, bad, bad])
    result = graph.run_analysis("Delete everything")
    assert result["status"] == "error"
    assert len(calls) == 3  # first try + 2 corrections, then stop
    assert "execute_sql" not in result["steps"]


def test_missing_api_key(monkeypatch):
    monkeypatch.setattr(graph, "get_api_key", lambda: None)
    result = graph.run_analysis("Total revenue?")
    assert result["status"] == "error"
    assert "API key" in result["final_answer"]
