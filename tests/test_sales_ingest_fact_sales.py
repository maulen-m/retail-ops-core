"""
Tests for fact_sales ingestion with v8 economics.

Ensures duplicate detection respects the DB unique key even if size metadata is missing.
"""

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from core.ingest.sales_ingest import ingest_sales_to_fact_sales


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            product_type TEXT,
            cogs_kzt REAL
        )
    """)
    conn.execute("""
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            size_order INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE fact_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT,
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL,
            product_type TEXT,
            channel TEXT,
            delivery_fee REAL,
            net_rev_unit REAL,
            line_net_rev REAL,
            cogs_unit REAL,
            cogs_line REAL,
            profit_unit REAL,
            profit_line REAL,
            channel_code TEXT,
            UNIQUE(order_id, kaspi_offer_name, sku_id, store_code)
        )
    """)
    conn.commit()
    conn.close()


def test_fact_sales_ingest_updates_existing_on_unique_key(tmp_path: Path) -> None:
    db_path = tmp_path / "fact_sales.db"
    _init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg, product_type, cogs_kzt) VALUES (?, ?, ?, ?, ?)",
        ("CL_LINE52_BLACK", 1.0, 0.5, "CL", 1000.0),
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size, size_order) VALUES (?, ?, ?, ?)",
        ("CL_LINE52_BLACK_M", "CL_LINE52_BLACK", "M", 2),
    )
    # Existing row has mismatched my_size to emulate prior bad ingest
    conn.execute(
        """
        INSERT INTO fact_sales (
            order_id, kaspi_offer_name, store_code, order_date, sku_key, sku_id, my_size,
            quantity, sell_price_kzt, product_type, channel, delivery_fee, net_rev_unit,
            line_net_rev, cogs_unit, cogs_line, profit_unit, profit_line, channel_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "ORD-1",
            "Offer A",
            "UNIVERSAL",
            "2026-01-10",
            "CL_LINE52_BLACK",
            "CL_LINE52_BLACK_M",
            "XL",
            1,
            15000.0,
            "CL",
            "Kaspi",
            500.0,
            14000.0,
            14000.0,
            1000.0,
            1000.0,
            13000.0,
            13000.0,
            "KSP",
        ),
    )
    conn.commit()
    conn.close()

    df = pd.DataFrame({
        "OrderID": ["ORD-1"],
        "Date": [date(2026, 1, 10)],
        "KASPI_OFFER_NAME": ["Offer A"],
        "SKU_ID": ["CL_LINE52_BLACK_M"],
        "SKU_key": ["CL_LINE52_BLACK"],
        "MY_SIZE": ["M"],
        "Quantity": [1],
        "Sell_price_kzt": [15000.0],
        "STORE_NAME": ["Universal"],
        "Return": [0],
    })
    xlsx_path = tmp_path / "crm.xlsx"
    df.to_excel(xlsx_path, sheet_name="SALES_KSP_CRM_1", index=False)

    stats = ingest_sales_to_fact_sales(
        xlsx_path=str(xlsx_path),
        db_path=db_path,
    )

    assert stats["updated"] == 1
    assert stats["inserted"] == 0

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT my_size FROM fact_sales WHERE order_id = ? AND sku_id = ?",
        ("ORD-1", "CL_LINE52_BLACK_M"),
    ).fetchone()
    conn.close()
    assert row[0] == "M"
