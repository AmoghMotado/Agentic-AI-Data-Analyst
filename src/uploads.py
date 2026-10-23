"""
Turns files uploaded in the Streamlit page into a SQLite database on the server.

Supported uploads:
- one SQLite database file (.db, .sqlite, .sqlite3), used as it is
- one or more CSV files, each becoming one table in a new SQLite database

The result is saved under data/uploads/ with a name made from the file
contents (a hash), so uploading the same file twice reuses the same database.
The agent then opens it read-only, exactly like the sample database.
"""

import hashlib
import io
import re
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import UPLOAD_DIR

SQLITE_EXTENSIONS = (".db", ".sqlite", ".sqlite3")
SQLITE_HEADER = b"SQLite format 3\x00"


class UploadError(ValueError):
    """Raised with a user-friendly message when an upload cannot be used."""


def clean_name(name, fallback="table"):
    """Makes a simple SQL-friendly name: 'Sales Data 2024' -> 'sales_data_2024'."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_").lower() or fallback
    if name[0].isdigit():
        name = f"{fallback}_{name}"
    return name


def _unique(name, used):
    candidate, n = name, 2
    while candidate in used:
        candidate, n = f"{name}_{n}", n + 1
    used.add(candidate)
    return candidate


def _target_path(files):
    digest = hashlib.sha256()
    for filename, data in files:
        digest.update(filename.encode())
        digest.update(data)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR / f"upload_{digest.hexdigest()[:16]}.db"


def _table_names(path):
    with sqlite3.connect(path) as conn:
        return [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )]


def _save_sqlite(data, target):
    if not data.startswith(SQLITE_HEADER):
        raise UploadError("This file is not a SQLite database.")
    target.write_bytes(data)
    try:
        conn = sqlite3.connect(target)
        try:
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise UploadError("The SQLite file is damaged.")
            # A database in WAL mode cannot be opened read-only on its own,
            # so switch it to the normal journal mode once, while we still can write.
            conn.execute("PRAGMA journal_mode=DELETE")
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        target.unlink(missing_ok=True)
        raise UploadError(f"The SQLite file could not be opened: {exc}") from exc
    except UploadError:
        target.unlink(missing_ok=True)
        raise


def _save_csvs(files, target):
    used = set()
    tables = []
    for filename, data in files:
        try:
            df = pd.read_csv(io.BytesIO(data))
        except Exception as exc:
            raise UploadError(f"Could not read {filename} as CSV: {exc}") from exc
        if df.empty or len(df.columns) == 0:
            raise UploadError(f"{filename} has no data.")
        # Simple column names make the generated SQL much more reliable
        used_columns = set()
        df.columns = [_unique(clean_name(c, "column"), used_columns) for c in df.columns]
        tables.append((_unique(clean_name(Path(filename).stem), used), df))

    temp = target.with_suffix(".tmp")
    temp.unlink(missing_ok=True)
    with sqlite3.connect(temp) as conn:
        for table, df in tables:
            df.to_sql(table, conn, index=False)
    conn.close()
    temp.replace(target)


def save_upload(files):
    """
    files: list of (filename, bytes) from the Streamlit uploader.
    Returns the path of a SQLite database ready for the agent.
    Raises UploadError with a message for the user if the files can't be used.
    """
    if not files:
        raise UploadError("No file was uploaded.")

    names = [filename.lower() for filename, _ in files]
    is_sqlite = [n.endswith(SQLITE_EXTENSIONS) for n in names]
    is_csv = [n.endswith(".csv") for n in names]

    if any(is_sqlite) and len(files) > 1:
        raise UploadError("Upload one SQLite file, or one or more CSV files, not both.")
    if not all(a or b for a, b in zip(is_sqlite, is_csv)):
        raise UploadError("Only SQLite (.db, .sqlite, .sqlite3) and CSV files are supported.")

    target = _target_path(files)
    if not target.exists():
        if is_sqlite[0]:
            _save_sqlite(files[0][1], target)
        else:
            _save_csvs(files, target)

    if not _table_names(target):
        target.unlink(missing_ok=True)
        raise UploadError("The database has no tables.")
    return target
