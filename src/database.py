"""
Database access with SQLAlchemy.

SQLAlchemy gives us an "engine": an object that knows how to open connections
to the database. We run SQL through it with text(...) and get rows back.

The engine here is READ-ONLY: SQLite itself refuses any write. This is our
second safety layer after the SQL validator (defence in depth).
"""

import sqlite3

from sqlalchemy import create_engine, text

from src.config import DB_PATH, MAX_ROWS

_engine = None


def database_exists(db_path=DB_PATH):
    return db_path.exists()


def get_engine(db_path=DB_PATH):
    """Creates (once) and returns a read-only SQLAlchemy engine for the SQLite file."""
    global _engine
    if _engine is None:
        if not database_exists(db_path):
            raise FileNotFoundError(
                f"Database not found at {db_path}. Run: python scripts/create_database.py"
            )
        # 'mode=ro' opens SQLite in read-only mode. We pass a 'creator' function
        # so SQLAlchemy uses exactly this sqlite3 connection setup.
        uri = f"file:{db_path.as_posix()}?mode=ro"
        _engine = create_engine(
            "sqlite://",
            creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False),
        )
    return _engine


def run_query(sql, max_rows=MAX_ROWS):
    """
    Executes a SQL query and returns (columns, rows, truncated).

    columns:   list of column names
    rows:      list of tuples (at most max_rows)
    truncated: True if the query had more rows than max_rows
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [tuple(row) for row in result.fetchmany(max_rows + 1)]
    truncated = len(rows) > max_rows
    return columns, rows[:max_rows], truncated
