"""
Build the ShopFlow demo dataset (synthetic e-commerce company).

Tables (SQLite warehouse — analytics-style, denormalized-ish):
  customers, products, orders, order_items, returns, support_tickets, web_sessions

Relatable KPIs students will query:
  - revenue, AOV, refund rate, repeat purchase rate
  - top products / categories
  - cart abandonment, support volume by category

Run once:  python data/build_shopflow.py
"""
from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker

random.seed(42)
Faker.seed(42)
fake = Faker()

DB_PATH = Path(__file__).parent / "shopflow.db"
N_CUSTOMERS = 800
N_PRODUCTS = 120
N_ORDERS = 4000
START = datetime(2025, 1, 1)
END = datetime(2026, 5, 1)

CATEGORIES = [
    ("Electronics", 25, 800),
    ("Home & Kitchen", 10, 200),
    ("Beauty", 5, 80),
    ("Apparel", 15, 150),
    ("Sports", 20, 300),
    ("Books", 8, 40),
    ("Toys", 10, 120),
]
COUNTRIES = ["US", "UK", "IN", "DE", "FR", "AU", "CA"]
CHANNELS = ["web", "mobile", "marketplace"]
TICKET_CATS = ["shipping", "refund", "product_defect", "billing", "account", "other"]


def rand_date(start=START, end=END) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE customers (
            customer_id   INTEGER PRIMARY KEY,
            name          TEXT,
            email         TEXT,
            country       TEXT,
            signup_date   DATE,
            segment       TEXT
        );
        CREATE TABLE products (
            product_id    INTEGER PRIMARY KEY,
            name          TEXT,
            category      TEXT,
            price         REAL,
            cost          REAL,
            active        INTEGER
        );
        CREATE TABLE orders (
            order_id      INTEGER PRIMARY KEY,
            customer_id   INTEGER,
            order_date    DATE,
            channel       TEXT,
            status        TEXT,
            total_amount  REAL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
        CREATE TABLE order_items (
            order_item_id INTEGER PRIMARY KEY,
            order_id      INTEGER,
            product_id    INTEGER,
            quantity      INTEGER,
            unit_price    REAL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        CREATE TABLE returns (
            return_id     INTEGER PRIMARY KEY,
            order_id      INTEGER,
            return_date   DATE,
            reason        TEXT,
            refund_amount REAL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );
        CREATE TABLE support_tickets (
            ticket_id     INTEGER PRIMARY KEY,
            customer_id   INTEGER,
            opened_at     DATETIME,
            category      TEXT,
            priority      TEXT,
            resolved      INTEGER,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
        CREATE TABLE web_sessions (
            session_id    INTEGER PRIMARY KEY,
            customer_id   INTEGER,
            session_date  DATE,
            channel       TEXT,
            pages_viewed  INTEGER,
            added_to_cart INTEGER,
            converted     INTEGER
        );
        """
    )

    # Customers
    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        customers.append((
            cid, fake.name(), fake.email(),
            random.choices(COUNTRIES, weights=[40, 15, 15, 8, 7, 8, 7])[0],
            rand_date(START, END - timedelta(days=30)).date().isoformat(),
            random.choices(["new", "returning", "vip"], weights=[60, 30, 10])[0],
        ))
    cur.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", customers)

    # Products
    products = []
    for pid in range(1, N_PRODUCTS + 1):
        cat, lo, hi = random.choice(CATEGORIES)
        price = round(random.uniform(lo, hi), 2)
        cost = round(price * random.uniform(0.4, 0.7), 2)
        products.append((
            pid, fake.unique.catch_phrase()[:50], cat, price, cost,
            1 if random.random() > 0.05 else 0,
        ))
    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", products)

    # Orders + items
    orders, items = [], []
    item_id = 1
    for oid in range(1, N_ORDERS + 1):
        cid = random.randint(1, N_CUSTOMERS)
        odate = rand_date()
        channel = random.choices(CHANNELS, weights=[55, 35, 10])[0]
        status = random.choices(
            ["completed", "completed", "completed", "cancelled", "refunded"],
            weights=[70, 10, 10, 5, 5],
        )[0]
        n_items = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        total = 0.0
        for _ in range(n_items):
            pid = random.randint(1, N_PRODUCTS)
            qty = random.choices([1, 2, 3], weights=[80, 15, 5])[0]
            unit_price = products[pid - 1][3]
            items.append((item_id, oid, pid, qty, unit_price))
            total += qty * unit_price
            item_id += 1
        orders.append((oid, cid, odate.date().isoformat(), channel, status, round(total, 2)))
    cur.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?)", orders)
    cur.executemany("INSERT INTO order_items VALUES (?,?,?,?,?)", items)

    # Returns (only for refunded/some completed)
    returns = []
    rid = 1
    for o in orders:
        oid, _cid, odate, _ch, status, total = o
        if status == "refunded" or (status == "completed" and random.random() < 0.04):
            ret_date = (datetime.fromisoformat(odate) + timedelta(days=random.randint(2, 30))).date().isoformat()
            returns.append((
                rid, oid, ret_date,
                random.choice(["damaged", "wrong_item", "not_as_described", "changed_mind", "late_delivery"]),
                round(total * random.uniform(0.3, 1.0), 2),
            ))
            rid += 1
    cur.executemany("INSERT INTO returns VALUES (?,?,?,?,?)", returns)

    # Support tickets
    tickets = []
    for tid in range(1, 600):
        tickets.append((
            tid, random.randint(1, N_CUSTOMERS),
            rand_date().isoformat(sep=" ", timespec="seconds"),
            random.choice(TICKET_CATS),
            random.choices(["low", "medium", "high"], weights=[50, 35, 15])[0],
            1 if random.random() > 0.2 else 0,
        ))
    cur.executemany("INSERT INTO support_tickets VALUES (?,?,?,?,?,?)", tickets)

    # Web sessions
    sessions = []
    for sid in range(1, 6000):
        added = 1 if random.random() < 0.25 else 0
        converted = 1 if added and random.random() < 0.4 else 0
        sessions.append((
            sid, random.randint(1, N_CUSTOMERS),
            rand_date().date().isoformat(),
            random.choices(CHANNELS, weights=[60, 35, 5])[0],
            random.randint(1, 30),
            added, converted,
        ))
    cur.executemany("INSERT INTO web_sessions VALUES (?,?,?,?,?,?,?)", sessions)

    conn.commit()
    conn.close()
    print(f"[ok] Built ShopFlow database at {DB_PATH}")
    print(f"     Tables: customers, products, orders, order_items, returns, support_tickets, web_sessions")


if __name__ == "__main__":
    main()
