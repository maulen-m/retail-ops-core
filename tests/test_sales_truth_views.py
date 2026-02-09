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


def test_view_sales_truth_excludes_fact_sales_on_overlapping_dates(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-V2-1", "2026-02-05", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 1, 1000, 300, 700, "DELIVERED", 0),
            ("ORD-V2-2", "2026-02-06", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 2, 2200, 600, 1600, "DELIVERED", 0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-FS-OVERLAP", "2026-02-05", "SKU_A", "SKU_A_L", "L", "ACMEWEAR", 10, 8000, 2500, 5500),
            ("ORD-FS-PRE", "2026-02-04", "SKU_A", "SKU_A_L", "L", "ACMEWEAR", 3, 2400, 900, 1500),
        ],
    )
    conn.commit()

    ensure_sales_truth_views(conn)

    daily = conn.execute(
        """
        SELECT sale_date, SUM(units) AS units, SUM(revenue_kzt) AS net_rev
        FROM view_sales_daily_truth
        GROUP BY sale_date
        ORDER BY sale_date
        """
    ).fetchall()
    conn.close()

    # Overlapping date (2026-02-05) must use v2 only and exclude fact_sales revenue/units.
    assert daily == [
        ("2026-02-04", 3.0, 2400.0),
        ("2026-02-05", 1.0, 1000.0),
        ("2026-02-06", 2.0, 2200.0),
    ]


def test_view_sales_truth_keeps_fact_sales_for_pre_v2_history_only(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-V2-1', '2026-02-10', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 1, 1500, 300, 1200, 'DELIVERED', 0)
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-FS-HIST", "2026-02-09", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 2, 1800, 600, 1200),
            ("ORD-FS-OVERLAP", "2026-02-10", "SKU_A", "SKU_A_M", "M", "ACMEWEAR", 7, 7000, 2100, 4900),
        ],
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    rows = conn.execute(
        """
        SELECT order_id, sale_date, source_table, units, net_rev_kzt
        FROM view_sales_line_truth
        ORDER BY sale_date, order_id
        """
    ).fetchall()
    conn.close()

    assert rows == [
        ("ORD-FS-HIST", "2026-02-09", "fact_sales", 2.0, 1800.0),
        ("ORD-V2-1", "2026-02-10", "sales_fact_v2", 1.0, 1500.0),
    ]


def test_cogs_fallback_from_fact_sales_still_works_without_fact_sales_revenue_union(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_schema(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, net_rev, cogs, profit, status, return_flag)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 10000, 0, 0, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, line_net_rev, cogs_line, profit_line)
        VALUES ('ORD-1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'M', 'ACMEWEAR', 2, 9000, 3200, 5800)
        """
    )
    conn.commit()

    ensure_sales_truth_views(conn)
    row = conn.execute(
        """
        SELECT cogs_kzt, cogs_source, source_table, net_rev_kzt
        FROM view_sales_line_truth
        WHERE order_id='ORD-1'
        """
    ).fetchone()
    conn.close()

    assert row == (3200.0, "fact_sales_fallback", "sales_fact_v2", 10000.0)
