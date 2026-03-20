from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from scripts.rebuild_sales_fact_v2_from_kaspi_entries import build_sales_fact_v2_rows_from_entries


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity REAL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT,
            api_updated_at TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            internal_status TEXT,
            kaspi_status TEXT,
            status_updated_at TEXT,
            actual_shipment_date TEXT,
            planned_shipment_date TEXT,
            created_at TEXT,
            delivery_cost REAL,
            delivery_cost_for_seller REAL
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT,
            order_id TEXT,
            store_code TEXT,
            offer_id TEXT,
            quantity REAL,
            total_price_kzt REAL
        );
        CREATE TABLE dim_kaspi_article_map (
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER
        );
        """
    )


def test_sale_date_prefers_status_updated_at(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, sku_key, sku_id, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at
        ) VALUES (
            'ORD-1', 'ACMEWEAR', 'SKU_A', 'SKU_A_L', 'L',
            1, 'COMPLETED', 'Выдан', '2026-02-25T11:11:11',
            '2026-02-24', '2026-02-24', '2026-02-20'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('E1', 'ORD-1', 'ACMEWEAR', 'OFFER-A', 1, 900)
        """
    )
    conn.commit()

    rows, _summary = build_sales_fact_v2_rows_from_entries(conn, as_of=date(2026, 2, 26), strict=True)
    conn.close()

    assert rows[0]["order_date"] == "2026-02-25"


def test_sale_date_falls_back_when_status_updated_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, sku_key, sku_id, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at
        ) VALUES (
            'ORD-2', 'ACMEWEAR', 'SKU_A', 'SKU_A_L', 'L',
            1, 'COMPLETED', 'Выдан', '',
            '2026-02-24', '2026-02-23', '2026-02-20'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('E2', 'ORD-2', 'ACMEWEAR', 'OFFER-A', 1, 900)
        """
    )
    conn.commit()

    rows, _summary = build_sales_fact_v2_rows_from_entries(conn, as_of=date(2026, 2, 26), strict=True)
    conn.close()

    assert rows[0]["order_date"] == "2026-02-24"
