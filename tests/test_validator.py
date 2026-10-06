import pytest

from src.sql_validator import validate_sql
from src.tools import execute_sql


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM orders",
    "select * from products limit 5;",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "SELECT * FROM products WHERE product_name = 'Drop; Delete'",  # keywords inside a string are fine
    "SELECT REPLACE(product_name, ' ', '_') FROM products",
])
def test_valid_queries_accepted(sql):
    assert validate_sql(sql) == (True, "")


@pytest.mark.parametrize("sql", [
    "INSERT INTO products VALUES (99, 'x', 'y', 1)",
    "UPDATE products SET unit_price = 0",
    "DELETE FROM orders",
    "DROP TABLE customers",
    "ALTER TABLE orders ADD COLUMN x TEXT",
    "CREATE TABLE x (id INTEGER)",
    "TRUNCATE TABLE orders",
    "ATTACH DATABASE 'other.db' AS other",
    "DETACH DATABASE other",
    "PRAGMA table_info(orders)",
    "SELECT * FROM orders; DROP TABLE orders",
    "WITH x AS (SELECT 1) DELETE FROM orders",
    "",
    "   -- only a comment",
])
def test_unsafe_queries_rejected(sql):
    is_valid, reason = validate_sql(sql)
    assert not is_valid
    assert reason


def test_tool_blocks_unsafe_sql():
    result = execute_sql.invoke({"query": "DROP TABLE orders"})
    assert result["ok"] is False
    assert "Blocked" in result["error"]


def test_tool_returns_rows():
    result = execute_sql.invoke({"query": "SELECT COUNT(*) AS total_orders FROM orders"})
    assert result["ok"] is True
    assert result["columns"] == ["total_orders"]
    assert result["rows"] == [(400,)]


def test_tool_reports_sql_errors():
    result = execute_sql.invoke({"query": "SELECT revenue FROM orders"})
    assert result["ok"] is False
    assert "no such column" in result["error"]
