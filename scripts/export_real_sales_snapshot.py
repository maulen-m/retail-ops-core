#!/usr/bin/env python3
"""
Export daily real-sales snapshot grouped by (date, sku_key, size) from sales_fact_v2.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_EXPORT_ROOT = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/Exports_db"
)


def _resolve_window(conn: sqlite3.Connection, start: str | None, end: str | None) -> tuple[str, str]:
    if start:
        start_date = start
    else:
        row = conn.execute(
            """
            SELECT MIN(date(order_date)) AS min_date
            FROM sales_fact_v2
            WHERE COALESCE(return_flag, 0) = 0
            """
        ).fetchone()
        start_date = row["min_date"] if row and row["min_date"] else date.today().isoformat()

    end_date = end or date.today().isoformat()
    if start_date > end_date:
        raise ValueError(f"Invalid window: start_date {start_date} > end_date {end_date}")
    return start_date, end_date


def _query_rows(conn: sqlite3.Connection, start_date: str, end_date: str):
    sql = """
    WITH RECURSIVE calendar(sale_date) AS (
      SELECT date(?)
      UNION ALL
      SELECT date(sale_date, '+1 day')
      FROM calendar
      WHERE sale_date < date(?)
    ),
    base AS (
      SELECT
        date(order_date) AS sale_date,
        TRIM(COALESCE(sku_key, '')) AS sku_key,
        TRIM(COALESCE(my_size, '')) AS size,
        TRIM(COALESCE(sku_id, '')) AS sku_id,
        order_id,
        COALESCE(quantity, 0) AS quantity,
        sell_price_kzt,
        net_rev,
        cogs,
        profit,
        delivery_fee
      FROM sales_fact_v2
      WHERE date(order_date) BETWEEN date(?) AND date(?)
        AND COALESCE(return_flag, 0) = 0
    ),
    grouped AS (
      SELECT
        sale_date,
        sku_key,
        size,
        MIN(sku_id) AS sku_id_sample,
        SUM(quantity) AS total_units,
        COUNT(DISTINCT order_id) AS order_count,
        COUNT(*) AS line_count,
        AVG(sell_price_kzt) AS avg_sell_price_kzt,
        AVG(net_rev) AS avg_net_rev,
        CASE WHEN SUM(quantity) = 0 THEN NULL
             ELSE SUM(COALESCE(sell_price_kzt, 0) * quantity) / SUM(quantity)
        END AS weighted_avg_sell_price_kzt,
        SUM(COALESCE(sell_price_kzt, 0) * quantity) AS total_gross_revenue_kzt,
        SUM(COALESCE(net_rev, 0)) AS total_net_rev_kzt,
        SUM(COALESCE(cogs, 0)) AS total_cogs_kzt,
        SUM(COALESCE(profit, 0)) AS total_profit_kzt,
        AVG(delivery_fee) AS avg_delivery_fee_kzt,
        CASE WHEN SUM(quantity) = 0 THEN NULL
             ELSE SUM(COALESCE(delivery_fee, 0) * quantity) / SUM(quantity)
        END AS weighted_avg_delivery_fee_kzt,
        SUM(COALESCE(delivery_fee, 0)) AS total_delivery_fee_kzt
      FROM base
      WHERE sku_key <> ''
      GROUP BY sale_date, sku_key, size
    ),
    sku_day AS (
      SELECT sale_date, sku_key, SUM(total_units) AS sku_day_units
      FROM grouped
      GROUP BY sale_date, sku_key
    ),
    has_sales AS (
      SELECT sale_date, COUNT(*) AS row_count
      FROM grouped
      GROUP BY sale_date
    )
    SELECT *
    FROM (
      SELECT
        g.sale_date,
        g.sku_key,
        g.size,
        g.sku_id_sample,
        1 AS is_active_day,
        g.total_units,
        g.order_count,
        g.line_count,
        sd.sku_day_units,
        CASE WHEN sd.sku_day_units = 0 THEN 0 ELSE g.total_units * 1.0 / sd.sku_day_units END AS size_unit_share,
        g.avg_sell_price_kzt,
        g.avg_net_rev,
        g.weighted_avg_sell_price_kzt,
        g.total_gross_revenue_kzt,
        g.total_net_rev_kzt,
        g.total_cogs_kzt,
        g.total_profit_kzt,
        g.avg_delivery_fee_kzt,
        g.weighted_avg_delivery_fee_kzt,
        g.total_delivery_fee_kzt
      FROM grouped g
      JOIN sku_day sd
        ON sd.sale_date = g.sale_date
       AND sd.sku_key = g.sku_key

      UNION ALL

      SELECT
        c.sale_date,
        'NO_SALES' AS sku_key,
        '' AS size,
        '' AS sku_id_sample,
        0 AS is_active_day,
        0 AS total_units,
        0 AS order_count,
        0 AS line_count,
        0 AS sku_day_units,
        0 AS size_unit_share,
        NULL AS avg_sell_price_kzt,
        NULL AS avg_net_rev,
        NULL AS weighted_avg_sell_price_kzt,
        0 AS total_gross_revenue_kzt,
        0 AS total_net_rev_kzt,
        0 AS total_cogs_kzt,
        0 AS total_profit_kzt,
        NULL AS avg_delivery_fee_kzt,
        NULL AS weighted_avg_delivery_fee_kzt,
        0 AS total_delivery_fee_kzt
      FROM calendar c
      LEFT JOIN has_sales hs
        ON hs.sale_date = c.sale_date
      WHERE COALESCE(hs.row_count, 0) = 0
    ) AS final_rows
    ORDER BY sale_date ASC, sku_key ASC, size ASC
    """
    return conn.execute(sql, (start_date, end_date, start_date, end_date)).fetchall()


def _write_csv_atomic(path: Path, rows, headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
    ) as tmp:
        writer = csv.writer(tmp)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row[h] for h in headers])
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export real-sales daily SKU-size snapshot CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--export-root",
        type=Path,
        default=DEFAULT_EXPORT_ROOT,
        help="Base export folder (contains real_sales_snapshots/)",
    )
    parser.add_argument(
        "--snapshot-ts",
        type=str,
        default=None,
        help="Snapshot timestamp folder (YYYYMMDD_HHMMSS). Default: now.",
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(f"DB not found: {args.db}")

    snapshot_ts = args.snapshot_ts or datetime.now().strftime("%Y%m%d_%H%M%S")

    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        start_date, end_date = _resolve_window(conn, args.start_date, args.end_date)
        rows = _query_rows(conn, start_date=start_date, end_date=end_date)

    folder = args.export_root / "real_sales_snapshots" / snapshot_ts
    filename = (
        f"sales_daily_sku_size_{start_date}_to_{end_date}_"
        f"real_sales_snapshot_{snapshot_ts}.csv"
    )
    out_path = folder / filename

    headers = [
        "sale_date",
        "sku_key",
        "size",
        "sku_id_sample",
        "is_active_day",
        "total_units",
        "order_count",
        "line_count",
        "sku_day_units",
        "size_unit_share",
        "avg_sell_price_kzt",
        "avg_net_rev",
        "weighted_avg_sell_price_kzt",
        "total_gross_revenue_kzt",
        "total_net_rev_kzt",
        "total_cogs_kzt",
        "total_profit_kzt",
        "avg_delivery_fee_kzt",
        "weighted_avg_delivery_fee_kzt",
        "total_delivery_fee_kzt",
    ]

    _write_csv_atomic(out_path, rows, headers)
    print(f"rows={len(rows)}")
    print(f"start_date={start_date}")
    print(f"end_date={end_date}")
    print(f"output={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
