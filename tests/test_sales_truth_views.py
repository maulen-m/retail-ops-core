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
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL
        );
        """
    )


def test_view_sales_line_truth_prefers_sales_fact_v2_on_overlap(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute("INSERT INTO dim_sku (sku_key, cogs_kzt) VALUES ('SKU_A', 700)")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 10000, 3000, 7000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 8000, 2000, 6000)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT net_rev_kzt, cogs_kzt, profit_kzt, source_table
        FROM view_sales_line_truth
        WHERE order_id='ORD-1'
        """
    ).fetchone()
    conn.close()

    assert row[0] == 10000
    assert row[1] == 3000
    assert row[2] == 7000
    assert row[3] == "sales_fact_v2"


def test_view_sales_daily_truth_uses_fact_sales_when_missing_in_sales_fact_v2(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute("INSERT INTO dim_sku (sku_key, cogs_kzt) VALUES ('SKU_B', 1000)")
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('ORD-2', '2026-02-08', 'SKU_B', 'SKU_B_L', 'L', 'ACMEWEAR', 3, 15000, 4500, 10500)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT units, revenue_kzt, cogs_kzt, profit_kzt
        FROM view_sales_daily_truth
        WHERE sale_date='2026-02-08' AND sku_key='SKU_B'
        """
    ).fetchone()
    conn.close()

    assert row[0] == 3
    assert row[1] == 15000
    assert row[2] == 4500
    assert row[3] == 10500
