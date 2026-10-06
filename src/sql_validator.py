"""
SQL validation: never run LLM-generated SQL without checking it first.

Rules:
1. Must not be empty.
2. Must be a single statement (no "SELECT ...; DROP TABLE ...").
3. Must start with SELECT or WITH.
4. Must not contain any write/admin keyword (INSERT, DROP, ATTACH, ...).

Text inside quotes is ignored for the keyword check, so a value like
WHERE product_name = 'Drop Ship Box' is not wrongly blocked.

The database connection is also read-only (see database.py), so even if
something slipped past these rules, SQLite would refuse to write.
"""

import re

FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "GRANT", "REVOKE",
]


def _remove_comments(sql):
    sql = re.sub(r"--[^\n]*", " ", sql)               # -- line comments
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)  # /* block comments */


def _remove_string_literals(sql):
    # Replace '...' and "..." contents with empty quotes
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def clean_sql(sql):
    """Removes comments, surrounding whitespace and one trailing semicolon."""
    sql = _remove_comments(sql or "").strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


def validate_sql(sql):
    """Returns (is_valid, reason). reason is empty when the query is valid."""
    cleaned = clean_sql(sql)
    if not cleaned:
        return False, "The query is empty."

    code_only = _remove_string_literals(cleaned)

    if ";" in code_only:
        return False, "Only one SQL statement is allowed."

    first_word = code_only.split()[0].upper()
    if first_word not in ("SELECT", "WITH"):
        return False, f"Only read-only SELECT queries are allowed (query starts with {first_word})."

    upper = code_only.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            return False, f"Unsafe keyword '{keyword}' is not allowed. This system is read-only."

    return True, ""
