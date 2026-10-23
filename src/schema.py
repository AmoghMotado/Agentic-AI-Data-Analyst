"""
Schema inspection: builds the text description of the database that we give
to the LLM. This is what makes the prompting "schema-aware".

Table and column names come from the real database (SQLAlchemy inspect), so
the LLM always sees what actually exists. This works for any SQLite file,
including one the user uploads.

For the built-in NovaMart sample we also add short business descriptions, so
the LLM knows, for example, how revenue is calculated. For an uploaded
database we cannot know the business meaning, so instead we show row counts
and a few example values of short text columns (e.g. region = North, South).
"""

from pathlib import Path

from sqlalchemy import inspect, text

from src.config import DB_PATH
from src.database import get_engine

# Business meaning of some columns in the SAMPLE database only.
COLUMN_NOTES = {
    "customers.region": "one of North, South, East, West",
    "customers.customer_segment": "one of Consumer, Corporate, Small Business",
    "products.category": "one of Electronics, Furniture, Office Supplies, Clothing, Home & Kitchen",
    "products.unit_price": "current list price in INR (do NOT use for revenue)",
    "orders.order_date": "text in 'YYYY-MM-DD' format; use strftime() for months/years",
    "order_items.unit_price": "price actually charged per unit in INR (use for revenue)",
}

EXTRA_RULES = [
    "Revenue / sales amount = SUM(order_items.quantity * order_items.unit_price).",
    "Region belongs to the customer: join orders to customers to filter or group by region.",
    "Data covers orders from 2024-01-01 to 2025-12-31. Currency is INR (₹).",
]

UPLOADED_RULES = [
    "This is a database uploaded by the user; there are no extra business notes.",
    "Wrap table or column names that contain spaces or symbols in double quotes.",
    "If a column's meaning or currency is unclear, do not guess: mark the question as ambiguous.",
]

# A text column with at most this many different values gets its values listed
MAX_EXAMPLE_VALUES = 10


def quote_name(name):
    """Safely quotes a table/column name for SQLite, e.g. my table -> "my table"."""
    return '"' + str(name).replace('"', '""') + '"'


def is_sample_database(db_path=None):
    return Path(db_path or DB_PATH).resolve() == Path(DB_PATH).resolve()


def _example_values(conn, table, column):
    """Returns the distinct values of a short text column, or None if there are too many."""
    sql = (f"SELECT DISTINCT {quote_name(column)} FROM {quote_name(table)} "
           f"WHERE {quote_name(column)} IS NOT NULL LIMIT {MAX_EXAMPLE_VALUES + 1}")
    values = [row[0] for row in conn.execute(text(sql))]
    if 0 < len(values) <= MAX_EXAMPLE_VALUES and all(isinstance(v, str) and len(v) <= 40 for v in values):
        return values
    return None


def get_schema_text(db_path=None):
    """Returns a plain-text schema description for the LLM prompt."""
    sample = is_sample_database(db_path)
    engine = get_engine(db_path)
    inspector = inspect(engine)
    lines = []
    with engine.connect() as conn:
        for table in inspector.get_table_names():
            if sample:
                lines.append(f"TABLE {table}")
            else:
                count = conn.execute(text(f"SELECT COUNT(*) FROM {quote_name(table)}")).scalar()
                lines.append(f"TABLE {table} ({count} rows)")
            primary_keys = inspector.get_pk_constraint(table).get("constrained_columns", [])
            foreign_keys = {
                fk["constrained_columns"][0]: f"{fk['referred_table']}.{fk['referred_columns'][0]}"
                for fk in inspector.get_foreign_keys(table)
                if fk["constrained_columns"] and fk["referred_columns"]
            }
            for column in inspector.get_columns(table):
                name = column["name"]
                details = [str(column["type"]) or "no type"]
                if name in primary_keys:
                    details.append("primary key")
                if name in foreign_keys:
                    details.append(f"references {foreign_keys[name]}")
                if sample:
                    note = COLUMN_NOTES.get(f"{table}.{name}")
                    if note:
                        details.append(note)
                else:
                    values = _example_values(conn, table, name)
                    if values:
                        details.append("values: " + ", ".join(values))
                lines.append(f"  - {name}: {', '.join(details)}")
            lines.append("")
    lines.append("NOTES")
    lines.extend(f"  - {rule}" for rule in (EXTRA_RULES if sample else UPLOADED_RULES))
    return "\n".join(lines)


def get_dataset_info(db_path=None):
    """Row count per table (and the date range for the sample), shown in the Streamlit sidebar."""
    engine = get_engine(db_path)
    info = {"tables": {}}
    with engine.connect() as conn:
        for table in inspect(engine).get_table_names():
            # Table names come from the database itself, and are quoted safely
            info["tables"][table] = conn.execute(text(f"SELECT COUNT(*) FROM {quote_name(table)}")).scalar()
        if is_sample_database(db_path):
            first, last = conn.execute(text("SELECT MIN(order_date), MAX(order_date) FROM orders")).one()
            info["date_range"] = f"{first} to {last}"
    return info
