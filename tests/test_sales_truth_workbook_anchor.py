from __future__ import annotations

import sqlite3
from pathlib import Path

from core.sales.truth_views import ensure_sales_truth_views


def _seed_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
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
            source_file TEXT
        );
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL,
            profit_line REAL
        );
        """
    )


def test_truth_views_apply_workbook_anchor_sale_date_and_revenue_ceiling(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE fact_sales_workbook_anchor (
            order_id TEXT,
            store_code TEXT,
            sale_date TEXT,
            quantity REAL,
            net_rev_kzt REAL,
            total_price_kzt REAL,
            source_file TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit, status, return_flag, source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DELIVERED', 0, ?)
        """,
        [
            ("ORD-1", "2026-02-05", "SKU_A", "SKU_A_L", "L", "Offer A", "ACMEWEAR", 1, 100, 0, 0, 100, 100, "OCEAN_DROP_ANCHOR"),
            ("ORD-1", "2026-02-05", "SKU_B", "SKU_B_L", "L", "Offer B", "ACMEWEAR", 1, 100, 0, 0, 100, 100, "OCEAN_DROP_ANCHOR"),
        ],
    )
    conn.execute(
        """
        INSERT INTO fact_sales_workbook_anchor
        (order_id, store_code, sale_date, quantity, net_rev_kzt, total_price_kzt, source_file)
        VALUES ('ORD-1', 'ACMEWEAR', '2026-02-06', 2, 150, 150, 'SALES_KSP_CRM_V3.xlsx')
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)

    rows = conn.execute(
        """
        SELECT sale_date, sku_key, units, net_rev_kzt
        FROM view_sales_line_truth
        WHERE order_id='ORD-1'
        ORDER BY sku_key
        """
    ).fetchall()
    daily = conn.execute(
        """
        SELECT sale_date, SUM(units), SUM(revenue_kzt)
        FROM view_sales_daily_truth
        WHERE store_code='ACMEWEAR'
        GROUP BY sale_date
        ORDER BY sale_date
        """
    ).fetchall()
    conn.close()

    assert rows == [
        ("2026-02-06", "SKU_A", 1.0, 75.0),
        ("2026-02-06", "SKU_B", 1.0, 75.0),
    ]
    assert daily == [("2026-02-06", 2.0, 150.0)]


def test_truth_views_keep_internal_values_when_workbook_anchor_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit, status, return_flag, source_file
        ) VALUES (
            'ORD-2', '2026-02-05', 'SKU_A', 'SKU_A_L', 'L', 'Offer A', 'ACMEWEAR',
            1, 100, 0, 0, 100, 100, 'DELIVERED', 0, 'KASPI_API_ENTRIES_REBUILD'
        )
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)

    row = conn.execute(
        """
        SELECT sale_date, units, net_rev_kzt
        FROM view_sales_line_truth
        WHERE order_id='ORD-2'
        """
    ).fetchone()
    conn.close()

    assert row == ("2026-02-05", 1.0, 100.0)


def test_truth_views_exclude_orders_quarantined_by_workbook_anchor(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.executescript(
        """
        CREATE TABLE fact_sales_workbook_anchor_quarantine (
            order_id TEXT,
            store_code TEXT,
            sale_dates TEXT,
            reason TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
            quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit, status, return_flag, source_file
        ) VALUES (
            'ORD-Q', '2026-02-16', 'SKU_A', 'SKU_A_L', 'L', 'Offer A', 'STOREB',
            1, 100, 0, 0, 100, 100, 'DELIVERED', 0, 'OCEAN_DROP_ANCHOR'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales_workbook_anchor_quarantine
        (order_id, store_code, sale_dates, reason)
        VALUES ('ORD-Q', 'STOREB', '2026-02-14|2026-02-15', 'MULTI_DATE')
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)

    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM view_sales_line_truth
        WHERE order_id='ORD-Q'
        """
    ).fetchone()
    conn.close()

    assert row == (0,)
