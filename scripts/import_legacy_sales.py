#!/usr/bin/env python3
"""
Import Legacy Sales: Transform fact_sales_raw → fact_sales with calculated economics.

This script:
1. Reads raw sales data from fact_sales_raw
2. Joins with dim_sku to get base_cost_cny and weight_kg
3. Calculates economics using core/calc/economics.py
4. Inserts/updates fact_sales with calculated values

Idempotent: Safe to re-run. Uses UPSERT on (order_id, sku_id, store_code).

Usage:
    python scripts/import_legacy_sales.py           # Process all records
    python scripts/import_legacy_sales.py --dry-run # Preview without changes
    python scripts/import_legacy_sales.py --limit 100  # Process first 100
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db
from core.calc.economics import calc_cogs, calc_delivery_fee, calc_net_rev


def get_raw_sales_with_sku_data(conn, limit: int | None = None) -> list[dict]:
    """
    Fetch raw sales joined with SKU dimension data.

    Returns rows with all columns needed for economics calculations.
    """
    query = """
        SELECT
            r.id as raw_id,
            r.order_id,
            r.store_code,
            r.order_date,
            r.sku_id,
            r.quantity,
            r.sell_price_kzt,
            r.delivery_fee_seller,
            r.channel,
            s.sku_key,
            s.my_size,
            d.product_type,
            d.base_cost_cny,
            d.weight_kg
        FROM fact_sales_raw r
        JOIN dim_sku_size s ON r.sku_id = s.sku_id
        JOIN dim_sku d ON s.sku_key = d.sku_key
        WHERE r.sku_id IS NOT NULL
        ORDER BY r.order_date, r.id
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor = conn.execute(query)
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def transform_to_fact_sales(raw_row: dict) -> dict:
    """
    Transform a raw sales row into a fact_sales row with calculated economics.

    Args:
        raw_row: Dict from get_raw_sales_with_sku_data()

    Returns:
        Dict ready for fact_sales insert
    """
    # Use seller delivery fee when available; fallback to matrix
    delivery_fee = raw_row.get("delivery_fee_seller")
    if delivery_fee is None or delivery_fee == 0:
        delivery_fee = calc_delivery_fee(
            raw_row["sell_price_kzt"],
            weight_kg=raw_row["weight_kg"],
            delivery_type="city",
        )

    cogs_unit = calc_cogs(raw_row["base_cost_cny"], raw_row["weight_kg"])
    net_rev_unit = calc_net_rev(
        raw_row["sell_price_kzt"],
        delivery_fee=delivery_fee,
        weight_kg=raw_row["weight_kg"],
        delivery_type="city",
        as_of_date=raw_row["order_date"],
    )
    profit_unit = net_rev_unit - cogs_unit

    return {
        "order_id": raw_row["order_id"],
        "store_code": raw_row["store_code"],
        "order_date": raw_row["order_date"],
        "sku_key": raw_row["sku_key"],
        "sku_id": raw_row["sku_id"],
        "quantity": raw_row["quantity"],
        "sell_price_kzt": raw_row["sell_price_kzt"],
        "product_type": raw_row["product_type"],
        "channel": raw_row["channel"] or "kaspi",
        "delivery_fee": delivery_fee,
        "net_rev_unit": net_rev_unit,
        "line_net_rev": net_rev_unit * raw_row["quantity"],
        "cogs_unit": cogs_unit,
        "cogs_line": cogs_unit * raw_row["quantity"],
        "profit_unit": profit_unit,
        "profit_line": profit_unit * raw_row["quantity"],
    }


def upsert_fact_sales(conn, records: list[dict], dry_run: bool = False) -> dict:
    """
    Insert or update records into fact_sales.

    Uses INSERT OR REPLACE on the unique constraint (order_id, sku_id, store_code).

    Args:
        conn: Database connection
        records: List of transformed records
        dry_run: If True, don't actually write

    Returns:
        Dict with counts: inserted, total
    """
    if not records:
        return {"inserted": 0, "total": 0}

    if dry_run:
        return {"inserted": 0, "total": len(records), "dry_run": True}

    sql = """
        INSERT OR REPLACE INTO fact_sales (
            order_id, store_code, order_date, sku_key, sku_id,
            quantity, sell_price_kzt, product_type, channel,
            delivery_fee, net_rev_unit, line_net_rev,
            cogs_unit, cogs_line, profit_unit, profit_line
        ) VALUES (
            :order_id, :store_code, :order_date, :sku_key, :sku_id,
            :quantity, :sell_price_kzt, :product_type, :channel,
            :delivery_fee, :net_rev_unit, :line_net_rev,
            :cogs_unit, :cogs_line, :profit_unit, :profit_line
        )
    """

    cursor = conn.executemany(sql, records)
    conn.commit()

    return {"inserted": cursor.rowcount, "total": len(records)}


def process_sales(
    limit: int | None = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Main processing function: Transform fact_sales_raw → fact_sales.

    Args:
        limit: Max records to process (None = all)
        dry_run: If True, preview without changes
        verbose: Print progress

    Returns:
        Dict with processing stats
    """
    with get_db() as conn:
        # Get raw data with SKU info
        if verbose:
            print("Fetching raw sales data...")
        raw_rows = get_raw_sales_with_sku_data(conn, limit)

        if verbose:
            print(f"Found {len(raw_rows)} records to process")

        if not raw_rows:
            return {
                "raw_count": 0,
                "transformed_count": 0,
                "inserted_count": 0,
                "skipped_count": 0,
            }

        # Transform each row
        if verbose:
            print("Calculating economics...")

        transformed = []
        skipped = []

        for row in raw_rows:
            # Skip rows with zero/null cost data
            if not row["base_cost_cny"] or not row["weight_kg"]:
                skipped.append(row)
                continue

            try:
                transformed.append(transform_to_fact_sales(row))
            except Exception as e:
                print(f"  Error processing order {row['order_id']}: {e}")
                skipped.append(row)

        if verbose:
            print(f"Transformed {len(transformed)} records")
            if skipped:
                print(f"Skipped {len(skipped)} records (missing cost/weight data)")

        # Upsert to fact_sales
        if verbose:
            print("Writing to fact_sales..." if not dry_run else "DRY RUN - no changes")

        result = upsert_fact_sales(conn, transformed, dry_run)

        if verbose:
            print(f"Completed: {result['total']} records processed")

        # Show sample for verification
        if verbose and transformed:
            sample = transformed[0]
            print("\nSample record:")
            print(f"  Order: {sample['order_id']}")
            print(f"  SKU: {sample['sku_key']} / {sample['sku_id']}")
            print(f"  Price: {sample['sell_price_kzt']:,.0f} KZT")
            print(f"  Delivery: {sample['delivery_fee']:,.0f} KZT")
            print(f"  COGS: {sample['cogs_unit']:,.2f} KZT")
            print(f"  Net Rev: {sample['net_rev_unit']:,.2f} KZT")
            print(f"  Profit: {sample['profit_unit']:,.2f} KZT")

        return {
            "raw_count": len(raw_rows),
            "transformed_count": len(transformed),
            "inserted_count": result["total"],
            "skipped_count": len(skipped),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Transform fact_sales_raw → fact_sales with economics"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without making changes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to process",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("Import Legacy Sales: fact_sales_raw → fact_sales")
    print("=" * 50)

    result = process_sales(
        limit=args.limit,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    print("\n" + "=" * 50)
    print("Summary:")
    print(f"  Raw records: {result['raw_count']}")
    print(f"  Transformed: {result['transformed_count']}")
    print(f"  Written: {result['inserted_count']}")
    print(f"  Skipped: {result['skipped_count']}")
    print("=" * 50)

    return 0 if result["inserted_count"] > 0 or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
