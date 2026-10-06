import pytest

from src.database import run_query
from src.schema import get_dataset_info, get_schema_text


def test_tables_and_row_counts():
    info = get_dataset_info()
    assert info["customers"] == 120
    assert info["products"] == 25
    assert info["orders"] == 400
    assert 400 < info["order_items"] < 1600


def test_joins_work():
    columns, rows, _ = run_query("""
        SELECT c.region, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        GROUP BY c.region ORDER BY revenue DESC
    """)
    assert columns == ["region", "revenue"]
    assert {row[0] for row in rows} == {"North", "South", "East", "West"}


def test_schema_text_lists_real_columns():
    schema = get_schema_text()
    for name in ["customers", "products", "orders", "order_items", "customer_segment", "quantity"]:
        assert name in schema


def test_connection_is_read_only():
    with pytest.raises(Exception):
        run_query("DELETE FROM customers")
