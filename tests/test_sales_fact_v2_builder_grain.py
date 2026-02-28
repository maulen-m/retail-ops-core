from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pytest

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
            ingested_at TEXT,
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


def test_builder_keeps_order_entry_grain_and_totals(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)

    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            order_id, store_code, kaspi_offer_name, sku_key, sku_id, my_size,
            quantity, internal_status, kaspi_status, status_updated_at,
            actual_shipment_date, planned_shipment_date, created_at, delivery_cost_for_seller
        ) VALUES (
            'ORD-1', 'ACMEWEAR', 'ignored', '', '', '',
            2, 'COMPLETED', 'Выдан', '2026-02-25T10:00:00',
            '2026-02-25', '2026-02-25', '2026-02-24', 100
        )
        """
    )

    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("E1", "ORD-1", "ACMEWEAR", "OFFER-A", 1, 1000),
            ("E2", "ORD-1", "ACMEWEAR", "OFFER-B", 2, 2000),
        ],
    )
    conn.executemany(
        """
        INSERT INTO dim_kaspi_article_map (store_code, kaspi_offer_name, sku_key, sku_id, active_flag)
        VALUES (?, ?, ?, ?, 1)
        """,
        [
            ("ACMEWEAR", "OFFER-A", "SKU_A", "SKU_A_L"),
            ("ACMEWEAR", "OFFER-B", "SKU_B", "SKU_B_M"),
        ],
    )
    conn.commit()

    rows, summary = build_sales_fact_v2_rows_from_entries(
        conn,
        as_of=date(2026, 2, 26),
        strict=True,
    )
    conn.close()

    assert summary["rows_built"] == 2
    assert [(r["kaspi_offer_name"], r["quantity"], r["net_rev"]) for r in rows] == [
        ("OFFER-A", 1, 966.67),
        ("OFFER-B", 2, 1933.33),
    ]


def test_builder_fails_closed_when_identity_missing_in_strict_mode(tmp_path: Path) -> None:
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
            'ORD-2', 'ACMEWEAR', '', '', '',
            1, 'COMPLETED', 'Выдан', '2026-02-25T10:00:00',
            '2026-02-25', '2026-02-25', '2026-02-24'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, offer_id, quantity, total_price_kzt)
        VALUES ('E3', 'ORD-2', 'ACMEWEAR', 'UNKNOWN-OFFER', 1, 1000)
        """
    )
    conn.commit()

    from scripts.rebuild_sales_fact_v2_from_kaspi_entries import RebuildError

    with pytest.raises(RebuildError, match="missing sku mapping"):
        build_sales_fact_v2_rows_from_entries(
            conn,
            as_of=date(2026, 2, 26),
            strict=True,
        )
    conn.close()
