from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.generate_business_insides import compute_sales_metrics


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            internal_status TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            returned_to_warehouse INTEGER,
            status_updated_at TEXT,
            planned_shipment_date TEXT
        );
        INSERT INTO fact_orders_kaspi
        (order_id, internal_status, quantity, unit_price_kzt, returned_to_warehouse, status_updated_at, planned_shipment_date)
        VALUES ('ORD-1', 'COMPLETED', 2, 1000, 0, '2026-02-26', '2026-02-26');

        CREATE VIEW view_sales_line_truth AS
        SELECT
            '2026-02-26' AS sale_date,
            '' AS sku_key,
            '' AS cogs_source,
            0.0 AS units,
            0.0 AS net_rev_kzt
        WHERE 0;

        CREATE VIEW view_sales_daily_truth AS
        SELECT '2026-02-26' AS sale_date, 0.0 AS units, 0.0 AS revenue_kzt, 0.0 AS cogs_kzt, 0.0 AS profit_kzt
        WHERE 0;
        """
    )
    conn.commit()
    conn.close()


def test_completed_revenue_fallback_disabled_in_strict_mode(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    monkeypatch.setattr("scripts.generate_business_insides.ensure_sales_truth_views", lambda _conn: None)

    non_strict = compute_sales_metrics(
        db_path=db,
        as_of="2026-02-26",
        allow_completed_revenue_fallback=True,
        archive_orders_globs=[],
    )
    strict_like = compute_sales_metrics(
        db_path=db,
        as_of="2026-02-26",
        allow_completed_revenue_fallback=False,
        archive_orders_globs=[],
    )

    non_strict_day = next(row for row in non_strict["last_7_days"] if row["date"] == "2026-02-26")
    strict_day = next(row for row in strict_like["last_7_days"] if row["date"] == "2026-02-26")
    assert non_strict_day["net_rev_kzt"] == 2000.0
    assert strict_day["net_rev_kzt"] is None


def test_completed_revenue_fallback_handles_single_sale_date_candidate(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            order_id TEXT,
            internal_status TEXT,
            quantity REAL,
            unit_price_kzt REAL,
            returned_to_warehouse INTEGER,
            status_updated_at TEXT
        );
        INSERT INTO fact_orders_kaspi
        (order_id, internal_status, quantity, unit_price_kzt, returned_to_warehouse, status_updated_at)
        VALUES ('ORD-1', 'COMPLETED', 2, 1000, 0, '2026-02-26');

        CREATE VIEW view_sales_line_truth AS
        SELECT
            '2026-02-26' AS sale_date,
            '' AS sku_key,
            '' AS cogs_source,
            0.0 AS units,
            0.0 AS net_rev_kzt
        WHERE 0;

        CREATE VIEW view_sales_daily_truth AS
        SELECT '2026-02-26' AS sale_date, 0.0 AS units, 0.0 AS revenue_kzt, 0.0 AS cogs_kzt, 0.0 AS profit_kzt
        WHERE 0;
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("scripts.generate_business_insides.ensure_sales_truth_views", lambda _conn: None)

    metrics = compute_sales_metrics(
        db_path=db,
        as_of="2026-02-26",
        allow_completed_revenue_fallback=True,
        archive_orders_globs=[],
    )

    day = next(row for row in metrics["last_7_days"] if row["date"] == "2026-02-26")
    assert day["net_rev_kzt"] == 2000.0
