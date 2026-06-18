#!/usr/bin/env python3
"""Validate that legacy fact_sales and daily aggregates are complete/current."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def _latest_required_date(as_of: date, fresh_within_days: int) -> str:
    return (as_of - timedelta(days=fresh_within_days)).isoformat()


def validate(
    *,
    db_path: Path = DB_PATH,
    as_of: date | None = None,
    fresh_within_days: int = 1,
) -> bool:
    as_of = as_of or date.today()
    min_latest_date = _latest_required_date(as_of, fresh_within_days)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    checks = []
    warnings = []

    # Check 1: Records with zero COGS
    cursor.execute(
        "SELECT COUNT(*) FROM fact_sales WHERE cogs_unit = 0 OR cogs_unit IS NULL"
    )
    zero_cogs = cursor.fetchone()[0]
    checks.append(("Records with zero COGS", zero_cogs, 0, "="))

    # Check 2: Records with zero profit (might be legitimate for some SKUs)
    cursor.execute("SELECT COUNT(*) FROM fact_sales WHERE profit_line = 0")
    zero_profit = cursor.fetchone()[0]
    checks.append(("Records with zero profit", zero_profit, 100, "<"))

    # Check 3: SKUs in fact_sales missing from dim_sku
    cursor.execute("""
        SELECT COUNT(DISTINCT f.sku_key)
        FROM fact_sales f
        LEFT JOIN dim_sku s ON f.sku_key = s.sku_key
        WHERE s.sku_key IS NULL
    """)
    orphan_skus = cursor.fetchone()[0]
    checks.append(("Orphan SKUs (in sales, not in dim)", orphan_skus, 0, "="))

    # Check 4: Negative profit records. Low-price sales can be real business
    # outcomes, so this is a warning rather than a completeness stopline.
    cursor.execute("SELECT COUNT(*) FROM fact_sales WHERE profit_line < 0")
    negative_profit = cursor.fetchone()[0]
    warnings.append(("Records with negative profit", negative_profit))

    # Check 5: dim_sku entries with sales but no COGS authority.
    # Current landed-cost authority can be either explicit cogs_kzt or
    # base_cost_cny + weight_kg formula inputs.
    cursor.execute("""
        SELECT COUNT(DISTINCT s.sku_key)
        FROM dim_sku s
        JOIN fact_sales f ON s.sku_key = f.sku_key
        WHERE NOT (
            COALESCE(s.cogs_kzt, 0) > 0
            OR (COALESCE(s.base_cost_cny, 0) > 0 AND COALESCE(s.weight_kg, 0) > 0)
        )
    """)
    skus_with_sales_no_cogs_authority = cursor.fetchone()[0]
    checks.append((
        "SKUs with sales but no COGS authority in dim_sku",
        skus_with_sales_no_cogs_authority,
        0,
        "=",
    ))

    # Check 6: fact_sales_daily consistency
    cursor.execute("""
        SELECT ABS(SUM(f.quantity) - (SELECT SUM(units) FROM fact_sales_daily))
        FROM fact_sales f
    """)
    daily_diff = cursor.fetchone()[0] or 0
    checks.append(("Daily aggregate unit difference", int(daily_diff), 10, "<"))

    # Check 7: Data freshness
    cursor.execute("SELECT MAX(order_date) FROM fact_sales")
    latest_date = cursor.fetchone()[0]
    checks.append(("Latest sale date", latest_date, min_latest_date, ">="))

    conn.close()

    print("=== DATA COMPLETENESS VALIDATION ===\n")
    all_pass = True

    for check in checks:
        name, value, target, op = check

        if op == "=":
            passed = value == target
        elif op == "<":
            passed = value < target
        elif op == ">=":
            passed = str(value) >= str(target)
        else:
            passed = False

        status = "✓" if passed else "✗"
        if not passed:
            all_pass = False

        print(f"{status} {name}: {value} (target: {op} {target})")

    for name, value in warnings:
        print(f"! {name}: {value} (warning only)")

    print(f"\n{'✓ All checks passed' if all_pass else '✗ Some checks failed'}")
    return all_pass


if __name__ == "__main__":
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--fresh-within-days", type=int, default=1)
    args = parser.parse_args()

    sys.exit(
        0
        if validate(
            db_path=args.db_path,
            as_of=args.as_of,
            fresh_within_days=args.fresh_within_days,
        )
        else 1
    )
