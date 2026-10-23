"""
Tests for uploading your own data (SQLite or CSV) from the Streamlit page.
The LLM is mocked, so no API key is needed.
"""

import sqlite3

import pytest

from src import graph, sql_generator, uploads
from src.database import run_query
from src.schema import get_dataset_info, get_schema_text
from src.sql_generator import SQLResponse
from src.tools import execute_sql
from src.uploads import UploadError, save_upload

SALES_CSV = b"Store Name,Month,Sales Amount\nAlpha,2025-01,100\nBeta,2025-01,250\nAlpha,2025-02,300\n"


@pytest.fixture(autouse=True)
def temp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path / "uploads")


def make_sqlite_bytes(tmp_path, wal=False):
    path = tmp_path / "shop.db"
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, color TEXT, price REAL)")
    conn.executemany("INSERT INTO items (color, price) VALUES (?, ?)", [("red", 5.0), ("blue", 7.5), ("red", 2.5)])
    conn.commit()
    conn.close()
    return path.read_bytes()


def test_csv_becomes_a_table_with_clean_names():
    db_path = save_upload([("Store Sales 2025.csv", SALES_CSV)])
    info = get_dataset_info(db_path)
    assert info["tables"] == {"store_sales_2025": 3}
    result = execute_sql.invoke({
        "query": "SELECT store_name, SUM(sales_amount) AS total FROM store_sales_2025 GROUP BY store_name ORDER BY total DESC",
        "db_path": str(db_path),
    })
    assert result["columns"] == ["store_name", "total"]
    assert result["rows"] == [("Alpha", 400), ("Beta", 250)]


def test_several_csvs_become_several_tables():
    db_path = save_upload([("sales.csv", SALES_CSV), ("stores.csv", b"store_name,city\nAlpha,Pune\nBeta,Goa\n")])
    assert set(get_dataset_info(db_path)["tables"]) == {"sales", "stores"}


def test_same_upload_reuses_the_same_database():
    assert save_upload([("sales.csv", SALES_CSV)]) == save_upload([("sales.csv", SALES_CSV)])


def test_sqlite_upload_is_used_as_is(tmp_path):
    db_path = save_upload([("shop.db", make_sqlite_bytes(tmp_path))])
    result = execute_sql.invoke({"query": "SELECT COUNT(*) AS n FROM items", "db_path": str(db_path)})
    assert result["rows"] == [(3,)]


def test_wal_mode_sqlite_upload_can_be_read(tmp_path):
    db_path = save_upload([("shop.sqlite", make_sqlite_bytes(tmp_path, wal=True))])
    assert get_dataset_info(db_path)["tables"] == {"items": 3}


def test_uploaded_database_is_read_only(tmp_path):
    db_path = save_upload([("shop.db", make_sqlite_bytes(tmp_path))])
    with pytest.raises(Exception):
        run_query("DELETE FROM items", db_path=db_path)


def test_schema_text_for_upload_shows_rows_and_example_values(tmp_path):
    db_path = save_upload([("shop.db", make_sqlite_bytes(tmp_path))])
    schema = get_schema_text(db_path)
    assert "TABLE items (3 rows)" in schema
    assert "values: red, blue" in schema
    assert "NovaMart" not in schema and "INR" not in schema


@pytest.mark.parametrize("files, message", [
    ([], "No file"),
    ([("notes.txt", b"hello")], "Only SQLite"),
    ([("fake.db", b"not a database")], "not a SQLite"),
    ([("a.db", b"x"), ("b.csv", SALES_CSV)], "not both"),
    ([("empty.csv", b"")], "Could not read"),
])
def test_bad_uploads_are_rejected(files, message):
    with pytest.raises(UploadError, match=message):
        save_upload(files)


def test_agent_answers_from_the_uploaded_database(monkeypatch):
    db_path = save_upload([("sales.csv", SALES_CSV)])
    schemas = []

    def fake_generate_sql(question, schema, previous_sql="", error=""):
        schemas.append(schema)
        return SQLResponse(status="answerable", message="",
                           sql="SELECT store_name, SUM(sales_amount) AS total FROM sales GROUP BY store_name ORDER BY total DESC")

    monkeypatch.setattr(graph, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(sql_generator, "generate_sql", fake_generate_sql)
    monkeypatch.setattr(sql_generator, "generate_insight", lambda *args: "Fake insight.")
    graph._app = None

    result = graph.run_analysis("Which store sold the most?", db_path)
    assert result["status"] == "done"
    assert "TABLE sales" in schemas[0]
    assert result["analysis"]["highest"]["store_name"] == "Alpha"
