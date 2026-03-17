from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.report_sales_truth_max_dates import build_sales_truth_max_dates_report


def test_build_sales_truth_max_dates_report_detects_workbook_anchor_binding(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                status_updated_at TEXT
            );
            CREATE TABLE sales_fact_v2 (
                order_id TEXT,
                order_date TEXT,
                status TEXT,
                return_flag INTEGER
            );
            CREATE TABLE fact_sales (order_id TEXT, order_date TEXT);
            CREATE TABLE fact_sales_external_ref (order_id TEXT, sale_date TEXT);
            CREATE TABLE fact_sales_workbook_anchor (order_id TEXT, sale_date TEXT);
            CREATE VIEW view_sales_line_truth AS
                SELECT 'A' AS order_id, '2026-03-05' AS sale_date;
            CREATE VIEW view_sales_daily_truth AS
                SELECT '2026-03-05' AS sale_date;
            """
        )
        conn.execute(
            "INSERT INTO fact_orders_kaspi VALUES ('1','2026-03-07T10:00:00','2026-03-08T09:00:00','2026-03-08T09:30:00')"
        )
        conn.execute("INSERT INTO sales_fact_v2 VALUES ('1','2026-03-07','DELIVERED',0)")
        conn.execute("INSERT INTO fact_sales VALUES ('old','2026-02-01')")
        conn.execute("INSERT INTO fact_sales_external_ref VALUES ('ref','2026-02-26')")
        conn.execute("INSERT INTO fact_sales_workbook_anchor VALUES ('1','2026-03-05')")
        conn.commit()
    finally:
        conn.close()

    owner_truth_path = tmp_path / "owner_truth_summary.json"
    owner_truth_path.write_text(json.dumps({"as_of": "2026-03-09", "truth_source": "webui_archive"}), encoding="utf-8")
    system_health_path = tmp_path / "system_health.json"
    system_health_path.write_text(json.dumps({"as_of": "2026-03-09", "truth_source": "webui_archive"}), encoding="utf-8")

    report = build_sales_truth_max_dates_report(
        as_of="2026-03-09",
        db_path=db_path,
        owner_truth_summary_path=owner_truth_path,
        system_health_path=system_health_path,
    )

    assert report["raw_max_dates"]["sales_fact_v2_delivered_max"] == "2026-03-07"
    assert report["published_max_dates"]["view_sales_daily_truth_max"] == "2026-03-05"
    assert report["raw_max_dates"]["fact_sales_workbook_anchor_max"] == "2026-03-05"
    assert report["derived"]["published_vs_raw_delivered_lag_days"] == 2
    assert report["derived"]["anchor_binding"] is True
