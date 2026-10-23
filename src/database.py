"""
Database access with SQLAlchemy.

SQLAlchemy gives us an "engine": an object that knows how to open connections
to the database. We run SQL through it with text(...) and get rows back.

The engines here are READ-ONLY: SQLite itself refuses any write. This is our
second safety layer after the SQL validator (defence in depth).

The app can work on more than one database file: the built-in sample
(data/sales.db) or a file the user uploaded. Every function takes an optional
db_path; leaving it out means "use the sample database".
"""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from src.config import DB_PATH, MAX_ROWS

# One read-only engine per database file, created on first use
_engines = {}


def database_exists(db_path=None):
    return Path(db_path or DB_PATH).exists()


def get_engine(db_path=None):
    """Creates (once per file) and returns a read-only SQLAlchemy engine for a SQLite file."""
    db_path = Path(db_path or DB_PATH).resolve()
    if db_path not in _engines:
        if not db_path.exists():
            raise FileNotFoundError(
                f"Database not found at {db_path}. Run: python scripts/create_database.py"
            )
        # 'mode=ro' opens SQLite in read-only mode. We pass a 'creator' function
        # so SQLAlchemy uses exactly this sqlite3 connection setup.
        uri = f"file:{db_path.as_posix()}?mode=ro"
        _engines[db_path] = create_engine(
            "sqlite://",
            creator=lambda: sqlite3.connect(uri, uri=True, check_same_thread=False),
        )
    return _engines[db_path]


def run_query(sql, max_rows=MAX_ROWS, db_path=None):
    """
    Executes a SQL query and returns (columns, rows, truncated).

    columns:   list of column names
    rows:      list of tuples (at most max_rows)
    truncated: True if the query had more rows than max_rows
    """
    engine = get_engine(db_path)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [tuple(row) for row in result.fetchmany(max_rows + 1)]
    truncated = len(rows) > max_rows
    return columns, rows[:max_rows], truncated
