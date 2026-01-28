import sqlite3
from pathlib import Path

from scripts.build_fact_sales_v16 import build_fact_sales_v16
from scripts.migrate_021_fact_sales_v16 import migrate


def _init_fact_sales_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                delivery_cost_for_seller REAL
            );
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL
            );
            CREATE TABLE dim_kaspi_article_map (
                store_code TEXT,
                kaspi_article TEXT,
                sku_key TEXT,
                sku_id TEXT
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT,
                my_size TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_fact_sales_schema_v16(tmp_path):
    db_path = tmp_path / "sales_v16.db"
    sqlite3.connect(str(db_path)).close()

    migrate(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(fact_sales_v16)").fetchall()]
    finally:
        conn.close()

    expected = [
        "entry_id",
        "order_id",
        "store_code",
        "offer_id",
        "sku_key",
        "sku_id",
        "quantity",
        "unit_price_kzt",
        "total_price_kzt",
        "delivery_fee_kzt",
        "net_rev_kzt",
        "source",
        "run_id",
        "created_at",
    ]
    assert cols == expected


def test_fact_sales_reconciles_to_entries(tmp_path, monkeypatch):
    db_path = tmp_path / "sales_v16.db"
    _init_fact_sales_db(db_path)
    migrate(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO dim_sku (sku_key) VALUES (?)",
            ("CL_NEW-CLO_MEN_T-SHIRT_WHITE",),
        )
        conn.execute(
            "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
            ("CL_NEW-CLO_MEN_T-SHIRT_WHITE_2XL", "CL_NEW-CLO_MEN_T-SHIRT_WHITE", "2XL"),
        )
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (store_code, kaspi_article, sku_key, sku_id)
            VALUES (?, ?, ?, ?)
            """,
            ("STOREB", "ARTICLE-2XL", "CL_NEW-CLO_MEN_T-SHIRT_WHITE", "CL_NEW-CLO_MEN_T-SHIRT_WHITE_2XL"),
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (order_id, store_code, kaspi_offer_name, sku_key, sku_id, quantity, unit_price_kzt, delivery_cost_for_seller)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ORD1", "STOREB", "Offer", None, None, 1, 15000, 500),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("E1", "ORD1", "STOREB", "ARTICLE-2XL", 1, 15000, 15000),
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("E2", "ORD1", "STOREB", "ARTICLE-2XL", 1, 15000, 15000),
        )
        conn.commit()
    finally:
        conn.close()

    build_fact_sales_v16(db_path=db_path, apply=True, run_id="TEST")

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT entry_id, sku_id, total_price_kzt FROM fact_sales_v16 ORDER BY entry_id").fetchall()
        total = conn.execute("SELECT SUM(total_price_kzt) FROM fact_sales_v16").fetchone()[0]
    finally:
        conn.close()

    assert rows == [
        ("E1", "CL_NEW-CLO_MEN_T-SHIRT_WHITE_2XL", 15000.0),
        ("E2", "CL_NEW-CLO_MEN_T-SHIRT_WHITE_2XL", 15000.0),
    ]
    assert total == 30000.0
