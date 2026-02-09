#!/usr/bin/env python3
"""Validate published sales COGS integrity for a recent window."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _window_bounds(as_of: str | None, days: int) -> tuple[str, str]:
    end = date.fromisoformat(as_of) if as_of else date.today()
    start = end - timedelta(days=max(1, int(days)) - 1)
    return start.isoformat(), end.isoformat()


def validate_cogs_integrity(
    *,
    db_path: Path,
    as_of: str | None = None,
    days: int = 30,
    max_unresolved_rows: int = 0,
    max_unresolved_skus: int = 0,
) -> dict[str, Any]:
    start, end = _window_bounds(as_of, days)
    errors: list[str] = []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        ensure_sales_truth_views(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN cogs_source='formula_full' THEN 1 ELSE 0 END) AS formula_rows,
                SUM(
                    CASE
                        WHEN cogs_source='unresolved' OR cogs_kzt IS NULL OR profit_kzt IS NULL
                            THEN 1
                        ELSE 0
                    END
                ) AS unresolved_rows,
                COUNT(
                    DISTINCT CASE
                        WHEN cogs_source='unresolved' OR cogs_kzt IS NULL OR profit_kzt IS NULL
                            THEN sku_key
                        ELSE NULL
                    END
                ) AS unresolved_skus
            FROM view_sales_line_truth
            WHERE date(sale_date) BETWEEN ? AND ?
            """,
            (start, end),
        ).fetchone()
    finally:
        conn.close()

    total_rows = int(row["total_rows"] or 0)
    formula_rows = int(row["formula_rows"] or 0)
    unresolved_rows = int(row["unresolved_rows"] or 0)
    unresolved_skus = int(row["unresolved_skus"] or 0)

    if total_rows <= 0:
        errors.append(f"no published sales rows found in window {start}..{end}")
    if unresolved_rows > int(max_unresolved_rows):
        errors.append(
            f"unresolved COGS rows exceed threshold: "
            f"{unresolved_rows} > {int(max_unresolved_rows)}"
        )
    if unresolved_skus > int(max_unresolved_skus):
        errors.append(
            f"unresolved COGS SKU count exceed threshold: "
            f"{unresolved_skus} > {int(max_unresolved_skus)}"
        )

    return {
        "ok": not errors,
        "errors": errors,
        "window_start": start,
        "window_end": end,
        "total_rows": total_rows,
        "formula_rows": formula_rows,
        "unresolved_rows": unresolved_rows,
        "unresolved_skus": unresolved_skus,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate published COGS integrity")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max-unresolved-rows", type=int, default=0)
    parser.add_argument("--max-unresolved-skus", type=int, default=0)
    args = parser.parse_args()

    report = validate_cogs_integrity(
        db_path=args.db,
        as_of=args.as_of,
        days=args.days,
        max_unresolved_rows=args.max_unresolved_rows,
        max_unresolved_skus=args.max_unresolved_skus,
    )
    print(
        "COGS integrity window="
        f"{report['window_start']}..{report['window_end']} "
        f"total_rows={report['total_rows']} "
        f"formula_rows={report['formula_rows']} "
        f"unresolved_rows={report['unresolved_rows']} "
        f"unresolved_skus={report['unresolved_skus']}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: COGS integrity passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
