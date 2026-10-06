"""
Creates the NovaMart sample sales database (data/sales.db).

Run from the project root:
    python scripts/create_database.py

All names are fictional and generated from small word lists.
A fixed random seed means every run produces exactly the same data.
"""

import random
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sales.db"

SEED = 42
NUM_CUSTOMERS = 120
NUM_ORDERS = 400

# ---------------------------------------------------------------------------
# Reference data (fictional)
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Vikram", "Isha",
    "Arjun", "Sneha", "Karan", "Pooja", "Nikhil", "Riya", "Siddharth", "Tara",
    "Aditya", "Neha", "Rahul", "Kavya",
]
LAST_NAMES = [
    "Sharma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Mehta", "Rao",
    "Joshi", "Kulkarni", "Singh", "Das", "Menon", "Shah", "Verma",
]

# region -> cities in that region
REGIONS = {
    "North": ["Delhi", "Chandigarh", "Lucknow", "Jaipur"],
    "South": ["Bengaluru", "Chennai", "Hyderabad", "Kochi"],
    "East": ["Kolkata", "Bhubaneswar", "Patna", "Guwahati"],
    "West": ["Mumbai", "Pune", "Ahmedabad", "Goa"],
}
# West gets more customers so it naturally becomes the top region
REGION_WEIGHTS = {"North": 0.25, "South": 0.25, "East": 0.15, "West": 0.35}

SEGMENTS = ["Consumer", "Corporate", "Small Business"]
SEGMENT_WEIGHTS = [0.55, 0.25, 0.20]

# (product_name, category, unit_price in INR)
PRODUCTS = [
    ("Wireless Mouse", "Electronics", 799),
    ("Mechanical Keyboard", "Electronics", 3499),
    ("27-inch Monitor", "Electronics", 14999),
    ("Bluetooth Headphones", "Electronics", 2999),
    ("USB-C Hub", "Electronics", 1899),
    ("Office Chair", "Furniture", 8999),
    ("Standing Desk", "Furniture", 21999),
    ("Bookshelf", "Furniture", 5499),
    ("Filing Cabinet", "Furniture", 6999),
    ("Desk Lamp", "Furniture", 1299),
    ("A4 Paper Pack", "Office Supplies", 349),
    ("Gel Pen Set", "Office Supplies", 199),
    ("Stapler", "Office Supplies", 249),
    ("Whiteboard", "Office Supplies", 2499),
    ("Notebook Pack", "Office Supplies", 299),
    ("Cotton T-Shirt", "Clothing", 599),
    ("Denim Jacket", "Clothing", 2499),
    ("Running Shoes", "Clothing", 3999),
    ("Formal Shirt", "Clothing", 1499),
    ("Winter Hoodie", "Clothing", 1799),
    ("Non-stick Pan", "Home & Kitchen", 1199),
    ("Electric Kettle", "Home & Kitchen", 1499),
    ("Mixer Grinder", "Home & Kitchen", 3999),
    ("Water Bottle", "Home & Kitchen", 399),
    ("Air Fryer", "Home & Kitchen", 6999),
]

# Products that sell less often in 2025, so "declining sales" questions
# have a real answer in the data.
DECLINING_PRODUCTS = {"Filing Cabinet", "Denim Jacket", "Mechanical Keyboard"}

START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

CREATE_TABLES_SQL = [
    """
    CREATE TABLE customers (
        customer_id      INTEGER PRIMARY KEY,
        customer_name    TEXT NOT NULL,
        region           TEXT NOT NULL,
        city             TEXT NOT NULL,
        customer_segment TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE products (
        product_id   INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL,
        category     TEXT NOT NULL,
        unit_price   REAL NOT NULL
    )
    """,
    """
    CREATE TABLE orders (
        order_id    INTEGER PRIMARY KEY,
        customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
        order_date  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE order_items (
        order_item_id INTEGER PRIMARY KEY,
        order_id      INTEGER NOT NULL REFERENCES orders(order_id),
        product_id    INTEGER NOT NULL REFERENCES products(product_id),
        quantity      INTEGER NOT NULL,
        unit_price    REAL NOT NULL
    )
    """,
]


def generate_customers(rng):
    customers = []
    used_names = set()
    regions = list(REGION_WEIGHTS)
    weights = list(REGION_WEIGHTS.values())
    for customer_id in range(1, NUM_CUSTOMERS + 1):
        # Keep names unique so questions about a customer are unambiguous
        while True:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        region = rng.choices(regions, weights)[0]
        customers.append({
            "customer_id": customer_id,
            "customer_name": name,
            "region": region,
            "city": rng.choice(REGIONS[region]),
            "customer_segment": rng.choices(SEGMENTS, SEGMENT_WEIGHTS)[0],
        })
    return customers


def generate_products():
    return [
        {"product_id": i, "product_name": name, "category": category, "unit_price": price}
        for i, (name, category, price) in enumerate(PRODUCTS, start=1)
    ]


def random_order_date(rng):
    """Random date, slightly more orders in 2025 and in Oct-Dec (festive season)."""
    while True:
        offset = rng.randint(0, (END_DATE - START_DATE).days)
        day = START_DATE + timedelta(days=offset)
        keep_probability = 0.8
        if day.year == 2025:
            keep_probability += 0.15
        if day.month in (10, 11, 12):
            keep_probability += 0.2
        if rng.random() < min(keep_probability, 1.0):
            return day


def generate_orders_and_items(rng, customers, products):
    orders = []
    items = []
    item_id = 1
    for order_id in range(1, NUM_ORDERS + 1):
        order_day = random_order_date(rng)
        customer = rng.choice(customers)
        orders.append({
            "order_id": order_id,
            "customer_id": customer["customer_id"],
            "order_date": order_day.isoformat(),  # stored as 'YYYY-MM-DD'
        })

        # Declining products are much less likely to be picked in 2025
        weights = [
            0.3 if (order_day.year == 2025 and p["product_name"] in DECLINING_PRODUCTS) else 1.0
            for p in products
        ]
        num_items = rng.randint(1, 4)
        chosen = set()
        while len(chosen) < num_items:
            chosen.add(rng.choices(range(len(products)), weights)[0])

        for index in sorted(chosen):
            product = products[index]
            # Price actually charged can include a small discount
            discount = rng.choice([1.0, 1.0, 1.0, 0.95, 0.9])
            items.append({
                "order_item_id": item_id,
                "order_id": order_id,
                "product_id": product["product_id"],
                "quantity": rng.choices([1, 2, 3, 4, 5], [0.5, 0.25, 0.12, 0.08, 0.05])[0],
                "unit_price": round(product["unit_price"] * discount, 2),
            })
            item_id += 1
    return orders, items


def create_database(db_path=DEFAULT_DB_PATH):
    """Deletes any old database file and builds a fresh one. Returns row counts."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    rng = random.Random(SEED)
    customers = generate_customers(rng)
    products = generate_products()
    orders, items = generate_orders_and_items(rng, customers, products)

    # This engine can write; the app itself uses a separate read-only engine.
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:  # begin() commits automatically at the end
        for statement in CREATE_TABLES_SQL:
            conn.execute(text(statement))
        conn.execute(
            text("INSERT INTO customers VALUES (:customer_id, :customer_name, :region, :city, :customer_segment)"),
            customers,
        )
        conn.execute(
            text("INSERT INTO products VALUES (:product_id, :product_name, :category, :unit_price)"),
            products,
        )
        conn.execute(
            text("INSERT INTO orders VALUES (:order_id, :customer_id, :order_date)"),
            orders,
        )
        conn.execute(
            text("INSERT INTO order_items VALUES (:order_item_id, :order_id, :product_id, :quantity, :unit_price)"),
            items,
        )
    engine.dispose()

    return {
        "customers": len(customers),
        "products": len(products),
        "orders": len(orders),
        "order_items": len(items),
    }


if __name__ == "__main__":
    counts = create_database()
    print(f"Database created at: {DEFAULT_DB_PATH}")
    for table, count in counts.items():
        print(f"  {table:<12} {count:>5} rows")
    print("Done.")
