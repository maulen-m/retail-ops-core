from __future__ import annotations

from pathlib import Path
import sqlite3

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
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
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
        CREATE TABLE fact_sales_external_ref (
            line_id TEXT PRIMARY KEY,
            sale_date TEXT,
            store_code TEXT,
            order_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            quantity REAL,
            net_rev_kzt REAL,
            status TEXT,
            return_flag INTEGER
        );
        """
    )


def test_truth_views_do_not_override_internal_with_external_reference(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)

    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-INT', '2026-02-25', 'SKU_INT', 'SKU_INT_L', 'L', 'Offer', 'ACMEWEAR', 1, 1000, 0, 1000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales_external_ref
        (line_id, sale_date, store_code, order_id, sku_key, sku_id, quantity, net_rev_kzt, status, return_flag)
        VALUES ('ref-1', '2026-02-25', 'ACMEWEAR', 'ORD-REF', 'SKU_REF', 'SKU_REF_L', 3, 5000, 'DELIVERED', 0)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)

    truth_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='view_sales_line_truth'"
    ).fetchone()[0]
    reference_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='view' AND name='view_sales_line_reference'"
    ).fetchone()[0]

    truth_daily = conn.execute(
        """
        SELECT SUM(units), SUM(revenue_kzt)
        FROM view_sales_daily_truth
        WHERE sale_date='2026-02-25' AND store_code='ACMEWEAR'
        """
    ).fetchone()
    reference_daily = conn.execute(
        """
        SELECT SUM(units), SUM(revenue_kzt)
        FROM view_sales_daily_reference
        WHERE sale_date='2026-02-25' AND store_code='ACMEWEAR'
        """
    ).fetchone()
    conn.close()

    assert "fact_sales_external_ref" not in truth_sql.lower()
    assert "fact_sales_external_ref" in reference_sql.lower()
    assert truth_daily == (1.0, 1000.0)
    assert reference_daily == (3.0, 5000.0)
