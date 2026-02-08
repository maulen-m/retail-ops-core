import sqlite3
from pathlib import Path

from scripts.validate_sales_truth_reconciliation import reconcile_sales_truth


def _seed_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            store_code TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE fact_sales (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            store_code TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL
        );
        """
    )


def test_reconciliation_reports_daily_mismatch_and_coverage_gap(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_tables(conn)
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, store_code, quantity, net_rev, cogs, status, return_flag)
        VALUES ('O1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'ACMEWEAR', 1, 5000, 0, 'DELIVERED', 0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_sales
        (order_id, order_date, sku_key, sku_id, store_code, quantity, line_net_rev, cogs_line)
        VALUES ('O1', '2026-02-08', 'SKU_A', 'SKU_A_M', 'ACMEWEAR', 2, 9000, 3000)
        """
    )
    conn.commit()
    conn.close()

    report = reconcile_sales_truth(db_path=db, days=7)
    assert report["window_days"] == 7
    assert report["daily_mismatch_count"] == 1
    assert report["sales_fact_v2"]["cogs_coverage_pct"] == 0.0
    assert report["fact_sales"]["cogs_coverage_pct"] == 100.0


def test_reconciliation_passes_when_sources_match(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    _seed_tables(conn)
    for table, net_col, cogs_col in (
        ("sales_fact_v2", "net_rev", "cogs"),
        ("fact_sales", "line_net_rev", "cogs_line"),
    ):
        conn.execute(
            f"""
            INSERT INTO {table}
            (order_id, order_date, sku_key, sku_id, store_code, quantity, {net_col}, {cogs_col}{", status, return_flag" if table == "sales_fact_v2" else ""})
            VALUES ('O2', '2026-02-08', 'SKU_B', 'SKU_B_L', 'ACMEWEAR', 2, 8000, 2400{", 'DELIVERED', 0" if table == "sales_fact_v2" else ""})
            """
        )
    conn.commit()
    conn.close()

    report = reconcile_sales_truth(db_path=db, days=7)
    assert report["daily_mismatch_count"] == 0
    assert report["sales_fact_v2"]["orders"] == report["fact_sales"]["orders"]
    assert report["sales_fact_v2"]["units"] == report["fact_sales"]["units"]
