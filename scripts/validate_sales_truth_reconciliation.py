#!/usr/bin/env python3
"""Reconcile staging sales sources over a recent window."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sqlite3
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _as_of_date(as_of: str | None) -> date:
    if as_of:
        return date.fromisoformat(as_of)
    return date.today()


def _source_metrics(conn: sqlite3.Connection, source: str, start: str, end: str) -> dict[str, Any]:
    if source == "sales_fact_v2":
        if not _table_exists(conn, "sales_fact_v2"):
            return {"present": False}
        rows = conn.execute(
            """
            SELECT
                date(order_date) AS d,
                COUNT(DISTINCT order_id) AS orders,
                SUM(COALESCE(quantity, 0)) AS units,
                SUM(COALESCE(net_rev, 0)) AS net_rev_kzt,
                SUM(COALESCE(cogs, 0)) AS cogs_kzt,
                SUM(CASE WHEN COALESCE(cogs, 0) > 0 THEN 1 ELSE 0 END) AS cogs_rows,
                COUNT(*) AS total_rows
            FROM sales_fact_v2
            WHERE date(order_date) BETWEEN ? AND ?
              AND UPPER(COALESCE(status, '')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0
            GROUP BY date(order_date)
            """,
            (start, end),
        ).fetchall()
    elif source == "fact_sales":
        if not _table_exists(conn, "fact_sales"):
            return {"present": False}
        rows = conn.execute(
            """
            SELECT
                date(order_date) AS d,
                COUNT(DISTINCT order_id) AS orders,
                SUM(COALESCE(quantity, 0)) AS units,
                SUM(COALESCE(line_net_rev, 0)) AS net_rev_kzt,
                SUM(COALESCE(cogs_line, 0)) AS cogs_kzt,
                SUM(CASE WHEN COALESCE(cogs_line, 0) > 0 THEN 1 ELSE 0 END) AS cogs_rows,
                COUNT(*) AS total_rows
            FROM fact_sales
            WHERE date(order_date) BETWEEN ? AND ?
            GROUP BY date(order_date)
            """,
            (start, end),
        ).fetchall()
    else:
        raise ValueError(f"Unknown source: {source}")

    daily: dict[str, dict[str, float]] = {}
    totals = {
        "orders": 0.0,
        "units": 0.0,
        "net_rev_kzt": 0.0,
        "cogs_kzt": 0.0,
        "cogs_rows": 0.0,
        "total_rows": 0.0,
    }
    for row in rows:
        d = str(row[0])
        daily[d] = {
            "orders": float(row[1] or 0.0),
            "units": float(row[2] or 0.0),
            "net_rev_kzt": float(row[3] or 0.0),
            "cogs_kzt": float(row[4] or 0.0),
        }
        totals["orders"] += float(row[1] or 0.0)
        totals["units"] += float(row[2] or 0.0)
        totals["net_rev_kzt"] += float(row[3] or 0.0)
        totals["cogs_kzt"] += float(row[4] or 0.0)
        totals["cogs_rows"] += float(row[5] or 0.0)
        totals["total_rows"] += float(row[6] or 0.0)

    coverage = (
        round((totals["cogs_rows"] / totals["total_rows"]) * 100.0, 2)
        if totals["total_rows"] > 0
        else 0.0
    )
    return {
        "present": True,
        "orders": int(round(totals["orders"])),
        "units": round(totals["units"], 2),
        "net_rev_kzt": round(totals["net_rev_kzt"], 2),
        "cogs_kzt": round(totals["cogs_kzt"], 2),
        "cogs_coverage_pct": coverage,
        "daily": daily,
    }


def reconcile_sales_truth(
    *,
    db_path: Path,
    days: int = 30,
    as_of: str | None = None,
    net_tolerance_kzt: float = 1.0,
    units_tolerance: float = 0.001,
) -> dict[str, Any]:
    as_of_date = _as_of_date(as_of)
    start = (as_of_date - timedelta(days=max(1, int(days)) - 1)).isoformat()
    end = as_of_date.isoformat()

    conn = sqlite3.connect(str(db_path))
    try:
        metrics_v2 = _source_metrics(conn, "sales_fact_v2", start, end)
        metrics_fs = _source_metrics(conn, "fact_sales", start, end)
    finally:
        conn.close()

    daily_mismatch_count = 0
    if metrics_v2.get("present") and metrics_fs.get("present"):
        all_days = sorted(set(metrics_v2["daily"].keys()) | set(metrics_fs["daily"].keys()))
        for d in all_days:
            v2 = metrics_v2["daily"].get(d, {"orders": 0.0, "units": 0.0, "net_rev_kzt": 0.0})
            fs = metrics_fs["daily"].get(d, {"orders": 0.0, "units": 0.0, "net_rev_kzt": 0.0})
            if (
                abs(v2["units"] - fs["units"]) > units_tolerance
                or abs(v2["net_rev_kzt"] - fs["net_rev_kzt"]) > net_tolerance_kzt
                or abs(v2["orders"] - fs["orders"]) > units_tolerance
            ):
                daily_mismatch_count += 1

    return {
        "as_of": end,
        "window_days": int(days),
        "daily_mismatch_count": daily_mismatch_count,
        "sales_fact_v2": {k: v for k, v in metrics_v2.items() if k != "daily"},
        "fact_sales": {k: v for k, v in metrics_fs.items() if k != "daily"},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate sales truth reconciliation")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--as-of", type=str, default=None)
    args = parser.parse_args()

    report = reconcile_sales_truth(
        db_path=args.db,
        days=args.days,
        as_of=args.as_of,
    )
    print(report)
    if not report["sales_fact_v2"].get("present") and not report["fact_sales"].get("present"):
        print("ERROR: missing both staging sales tables")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
