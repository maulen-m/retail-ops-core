#!/usr/bin/env python3
"""
Build Daily Aggregates: Rebuild fact_sales_daily and fact_sales_daily_size from fact_sales.

This script aggregates transaction-level data into daily summaries:

fact_sales_daily (style-level):
- Grain: (sale_date, store_code, sku_key)
- Aggregates: units, revenue, cogs, profit

fact_sales_daily_size (size-level):
- Grain: (sale_date, store_code, sku_id)
- Aggregates: units

Idempotent: Uses DELETE + INSERT for complete rebuild or date range.

Usage:
    python scripts/build_daily_aggregates.py           # Rebuild all
    python scripts/build_daily_aggregates.py --from 2024-09-01  # From date
    python scripts/build_daily_aggregates.py --from 2024-09-01 --to 2024-09-30  # Range
    python scripts/build_daily_aggregates.py --dry-run # Preview SQL
"""

import argparse
import sys
from pathlib import Path
from datetime import date

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db


def build_fact_sales_daily(
    conn,
    from_date: str | None = None,
    to_date: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Rebuild fact_sales_daily from fact_sales.

    Groups by (order_date, store_code, sku_key) and sums:
    - units (quantity)
    - revenue (line_net_rev)
    - cogs (cogs_line)
    - profit (profit_line)

    Args:
        conn: Database connection
        from_date: Start date (inclusive), ISO format
        to_date: End date (inclusive), ISO format
        dry_run: If True, show SQL without executing

    Returns:
        Dict with stats: deleted, inserted
    """
    # Build WHERE clause for date range
    where_clause = ""
    params = {}
    if from_date:
        where_clause = "WHERE order_date >= :from_date"
        params["from_date"] = from_date
        if to_date:
            where_clause += " AND order_date <= :to_date"
            params["to_date"] = to_date
    elif to_date:
        where_clause = "WHERE order_date <= :to_date"
        params["to_date"] = to_date

    # Delete existing records in range (for idempotency)
    delete_where = where_clause.replace("order_date", "sale_date")
    delete_sql = f"DELETE FROM fact_sales_daily {delete_where}"

    # Insert aggregated data
    insert_sql = f"""
        INSERT INTO fact_sales_daily (sale_date, store_code, sku_key, units, revenue, cogs, profit)
        SELECT
            order_date as sale_date,
            store_code,
            sku_key,
            SUM(quantity) as units,
            SUM(line_net_rev) as revenue,
            SUM(cogs_line) as cogs,
            SUM(profit_line) as profit
        FROM fact_sales
        {where_clause}
        GROUP BY order_date, store_code, sku_key
    """

    if dry_run:
        print("DELETE SQL:")
        print(delete_sql)
        print("\nINSERT SQL:")
        print(insert_sql)
        print(f"\nParams: {params}")
        return {"deleted": 0, "inserted": 0, "dry_run": True}

    # Execute
    cursor = conn.execute(delete_sql, params)
    deleted = cursor.rowcount

    cursor = conn.execute(insert_sql, params)
    inserted = cursor.rowcount

    conn.commit()

    return {"deleted": deleted, "inserted": inserted}


def build_fact_sales_daily_size(
    conn,
    from_date: str | None = None,
    to_date: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Rebuild fact_sales_daily_size from fact_sales.

    Groups by (order_date, store_code, sku_id) and sums:
    - units (quantity)

    Args:
        conn: Database connection
        from_date: Start date (inclusive), ISO format
        to_date: End date (inclusive), ISO format
        dry_run: If True, show SQL without executing

    Returns:
        Dict with stats: deleted, inserted
    """
    # Build WHERE clause for date range
    where_clause = ""
    params = {}
    if from_date:
        where_clause = "WHERE order_date >= :from_date"
        params["from_date"] = from_date
        if to_date:
            where_clause += " AND order_date <= :to_date"
            params["to_date"] = to_date
    elif to_date:
        where_clause = "WHERE order_date <= :to_date"
        params["to_date"] = to_date

    # Delete existing records in range
    delete_where = where_clause.replace("order_date", "sale_date")
    delete_sql = f"DELETE FROM fact_sales_daily_size {delete_where}"

    # Insert aggregated data
    insert_sql = f"""
        INSERT INTO fact_sales_daily_size (sale_date, store_code, sku_id, units)
        SELECT
            order_date as sale_date,
            store_code,
            sku_id,
            SUM(quantity) as units
        FROM fact_sales
        {where_clause}
        GROUP BY order_date, store_code, sku_id
    """

    if dry_run:
        print("DELETE SQL:")
        print(delete_sql)
        print("\nINSERT SQL:")
        print(insert_sql)
        print(f"\nParams: {params}")
        return {"deleted": 0, "inserted": 0, "dry_run": True}

    # Execute
    cursor = conn.execute(delete_sql, params)
    deleted = cursor.rowcount

    cursor = conn.execute(insert_sql, params)
    inserted = cursor.rowcount

    conn.commit()

    return {"deleted": deleted, "inserted": inserted}


def build_all_aggregates(
    from_date: str | None = None,
    to_date: str | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Build both daily aggregate tables.

    Args:
        from_date: Start date (inclusive), ISO format
        to_date: End date (inclusive), ISO format
        dry_run: If True, show SQL without executing
        verbose: Print progress

    Returns:
        Dict with stats for both tables
    """
    with get_db() as conn:
        # Build fact_sales_daily
        if verbose:
            print("Building fact_sales_daily...")
        daily_result = build_fact_sales_daily(conn, from_date, to_date, dry_run)
        if verbose:
            print(f"  Deleted: {daily_result['deleted']}, Inserted: {daily_result['inserted']}")

        # Build fact_sales_daily_size
        if verbose:
            print("\nBuilding fact_sales_daily_size...")
        size_result = build_fact_sales_daily_size(conn, from_date, to_date, dry_run)
        if verbose:
            print(f"  Deleted: {size_result['deleted']}, Inserted: {size_result['inserted']}")

        # Show summary stats
        if verbose and not dry_run:
            print("\nSummary stats:")

            # Date range in data
            cursor = conn.execute("""
                SELECT MIN(sale_date) as min_date, MAX(sale_date) as max_date, COUNT(*) as days
                FROM (SELECT DISTINCT sale_date FROM fact_sales_daily)
            """)
            row = cursor.fetchone()
            print(f"  Date range: {row[0]} to {row[1]} ({row[2]} unique days)")

            # Top SKUs by units
            cursor = conn.execute("""
                SELECT sku_key, SUM(units) as total_units, SUM(profit) as total_profit
                FROM fact_sales_daily
                GROUP BY sku_key
                ORDER BY total_units DESC
                LIMIT 5
            """)
            print("\n  Top 5 SKUs by units:")
            for row in cursor.fetchall():
                print(f"    {row[0]}: {row[1]:,} units, {row[2]:,.0f} KZT profit")

        return {
            "fact_sales_daily": daily_result,
            "fact_sales_daily_size": size_result,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild daily aggregate tables from fact_sales"
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        default=None,
        help="Start date (inclusive), ISO format (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=str,
        default=None,
        help="End date (inclusive), ISO format (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview SQL without making changes",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("Build Daily Aggregates")
    print("=" * 50)

    if args.from_date or args.to_date:
        print(f"Date range: {args.from_date or 'start'} to {args.to_date or 'end'}")

    if args.dry_run:
        print("DRY RUN - No changes will be made\n")

    result = build_all_aggregates(
        from_date=args.from_date,
        to_date=args.to_date,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 50)
    print("Completed!")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
