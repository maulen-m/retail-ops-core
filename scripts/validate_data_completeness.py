#!/usr/bin/env python3
"""
Validate that all sales records have valid COGS and economics.

Run: python scripts/validate_data_completeness.py

TASK-073
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def validate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    checks = []

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

    # Check 4: Negative profit records
    cursor.execute("SELECT COUNT(*) FROM fact_sales WHERE profit_line < 0")
    negative_profit = cursor.fetchone()[0]
    checks.append(("Records with negative profit", negative_profit, 50, "<"))

    # Check 5: dim_sku entries with sales but no COGS
    cursor.execute("""
        SELECT COUNT(DISTINCT s.sku_key)
        FROM dim_sku s
        JOIN fact_sales f ON s.sku_key = f.sku_key
        WHERE s.cogs_kzt IS NULL OR s.cogs_kzt = 0
    """)
    skus_with_sales_no_cogs = cursor.fetchone()[0]
    checks.append(("SKUs with sales but no COGS in dim_sku", skus_with_sales_no_cogs, 0, "="))

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
    checks.append(("Latest sale date", latest_date, "2025-12-01", ">="))

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

    print(f"\n{'✓ All checks passed' if all_pass else '✗ Some checks failed'}")
    return all_pass


if __name__ == "__main__":
    import sys
    sys.exit(0 if validate() else 1)
