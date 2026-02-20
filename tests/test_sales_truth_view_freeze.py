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
            base_cost_cny REAL,
            weight_kg REAL
        );
        """
    )


def test_published_truth_freezes_to_v2_on_and_after_v2_min_date(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU_A', 40, 0.5)"
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('V2-1', '2026-02-05', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 1, 1000, 100, 900, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('FS-OVERLAP', '2026-02-05', 'SKU_A', 'SKU_A_L', 'L', 'ACMEWEAR', 9, 9000, 900, 8100)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT SUM(units), SUM(revenue_kzt)
        FROM view_sales_daily_truth
        WHERE sale_date='2026-02-05'
        """
    ).fetchone()
    conn.close()

    assert row == (1.0, 1000.0)


def test_published_truth_uses_fact_sales_for_pre_v2_history(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        "INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU_A', 40, 0.5)"
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('V2-1', '2026-02-05', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 1, 1000, 100, 900, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('FS-HIST', '2026-02-04', 'SKU_A', 'SKU_A_L', 'L', 'ACMEWEAR', 3, 3000, 300, 2700)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT SUM(units), SUM(revenue_kzt)
        FROM view_sales_daily_truth
        WHERE sale_date='2026-02-04'
        """
    ).fetchone()
    conn.close()

    assert row == (3.0, 3000.0)
