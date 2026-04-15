from __future__ import annotations

import sqlite3
from pathlib import Path

from core.sales.truth_views import ensure_sales_truth_views


def test_view_sales_line_truth_excludes_rows_marked_returned_in_order_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                order_id TEXT,
                order_date TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                store_code TEXT,
                quantity REAL,
                net_rev REAL,
                cogs REAL,
                profit REAL,
                status TEXT,
                return_flag INTEGER
            );
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                internal_status TEXT
            );
            CREATE TABLE dim_sku (
                sku_key TEXT,
                base_cost_cny REAL,
                weight_kg REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, store_code,
                quantity, net_rev, cogs, profit, status, return_flag
            ) VALUES ('ORD_RET', '2026-02-18', 'SKU1', 'SKU1_XL', 'XL', 'UNIVERSAL', 1, 10000, 4000, 6000, 'DELIVERED', 0)
            """
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (order_id, store_code, internal_status)
            VALUES ('ORD_RET', 'UNIVERSAL', 'RETURNED')
            """
        )
        conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU1', 10, 0.5)")
        ensure_sales_truth_views(conn)
        rows = conn.execute("SELECT order_id FROM view_sales_line_truth").fetchall()
        assert rows == []
    finally:
        conn.close()
