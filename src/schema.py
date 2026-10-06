"""
Schema inspection: builds the text description of the database that we give
to the LLM. This is what makes the prompting "schema-aware".

Table and column names come from the real database (SQLAlchemy inspect), so
the LLM always sees what actually exists. Short business descriptions are
added so the LLM knows, for example, how revenue is calculated.
"""

from sqlalchemy import inspect, text

from src.database import get_engine

# Business meaning of some columns. Names and types still come from the database.
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


def get_schema_text():
    """Returns a plain-text schema description for the LLM prompt."""
    inspector = inspect(get_engine())
    lines = []
    for table in inspector.get_table_names():
        lines.append(f"TABLE {table}")
        primary_keys = inspector.get_pk_constraint(table).get("constrained_columns", [])
        foreign_keys = {
            fk["constrained_columns"][0]: f"{fk['referred_table']}.{fk['referred_columns'][0]}"
            for fk in inspector.get_foreign_keys(table)
        }
        for column in inspector.get_columns(table):
            name = column["name"]
            details = [str(column["type"])]
            if name in primary_keys:
                details.append("primary key")
            if name in foreign_keys:
                details.append(f"references {foreign_keys[name]}")
            note = COLUMN_NOTES.get(f"{table}.{name}")
            if note:
                details.append(note)
            lines.append(f"  - {name}: {', '.join(details)}")
        lines.append("")
    lines.append("NOTES")
    lines.extend(f"  - {rule}" for rule in EXTRA_RULES)
    return "\n".join(lines)


def get_dataset_info():
    """Row counts and date range, shown in the Streamlit sidebar."""
    engine = get_engine()
    info = {}
    with engine.connect() as conn:
        for table in inspect(engine).get_table_names():
            # Table names come from the database itself, not from user input
            info[table] = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        first, last = conn.execute(text("SELECT MIN(order_date), MAX(order_date) FROM orders")).one()
    info["date_range"] = f"{first} to {last}"
    return info
