#!/usr/bin/env python3
"""
Compare Old vs New Allocation: Phase 9.6 comparison report.

TASK-169: Side-by-side comparison of legacy vs Phase 9.6 allocation.

This script compares:
1. Legacy allocation (90-day historical mix)
2. Phase 9.6 allocation (size-aware with guardrails, OOS filtering, ROIC gate)

Output:
- Per-SKU comparison table
- Aggregate statistics
- Differences by size

Usage:
    python scripts/compare_old_vs_new_allocation.py                    # Compare all SKUs
    python scripts/compare_old_vs_new_allocation.py --sku LINE52      # Compare specific SKU
    python scripts/compare_old_vs_new_allocation.py --output report.csv
    python scripts/compare_old_vs_new_allocation.py --verbose
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db
from core.db.queries import (
    get_size_sales_history,
    get_size_stock_history,
    get_size_current_stock,
    get_size_inbound,
    get_size_sales_90d,
    get_sku_age_days,
)
from core.config.inventory_params import get_params
from core.calc.size_allocation import (
    generate_po_draft,
    calc_size_mix_with_guardrails,
)


# Standard size order
SIZE_ORDER = ["S", "M", "L", "XL", "2XL", "3XL", "4XL"]


def get_legacy_allocation(
    size_sales_90d: dict[str, int],
    total_order_qty: int
) -> dict[str, int]:
    """
    Calculate legacy allocation using 90-day historical mix.

    This is the old method: simple proportional allocation based on
    historical sales without guardrails.

    Args:
        size_sales_90d: Units sold per size in last 90 days
        total_order_qty: Total quantity to allocate

    Returns:
        Dict mapping size -> allocated quantity
    """
    total_sales = sum(size_sales_90d.values())

    if total_sales == 0:
        # Equal distribution fallback
        n_sizes = len(size_sales_90d)
        if n_sizes == 0:
            return {}
        per_size = total_order_qty // n_sizes
        allocation = {s: per_size for s in size_sales_90d}
        # Distribute remainder
        remainder = total_order_qty - sum(allocation.values())
        for size in list(allocation.keys())[:remainder]:
            allocation[size] += 1
        return allocation

    # Proportional allocation
    allocation = {}
    remainders = {}

    for size, sales in size_sales_90d.items():
        mix = sales / total_sales
        exact = total_order_qty * mix
        floor_val = int(exact)
        allocation[size] = floor_val
        remainders[size] = exact - floor_val

    # Distribute remainder using largest remainder method
    allocated = sum(allocation.values())
    remaining = total_order_qty - allocated

    sorted_sizes = sorted(remainders.keys(), key=lambda s: -remainders[s])
    for i in range(remaining):
        size = sorted_sizes[i % len(sorted_sizes)]
        allocation[size] += 1

    return allocation


def compare_sku(
    sku_key: str,
    verbose: bool = False
) -> Optional[dict]:
    """
    Compare old vs new allocation for a single SKU.

    Args:
        sku_key: SKU key to compare
        verbose: Show detailed output

    Returns:
        Dict with comparison data, or None if SKU has no data
    """
    import statistics

    with get_db() as conn:
        # Get size data
        size_current = get_size_current_stock(sku_key, "UNIVERSAL")

        if not size_current:
            if verbose:
                print(f"  {sku_key}: No size data found")
            return None

        sizes = list(size_current.keys())
        size_sales_history = get_size_sales_history(sku_key, "UNIVERSAL", days=90)
        size_stock_history = get_size_stock_history(sku_key, "UNIVERSAL", days=90)
        size_sales_90d = get_size_sales_90d(sku_key, "UNIVERSAL")
        size_inbound = get_size_inbound(sku_key, "UNIVERSAL")
        sku_age = get_sku_age_days(sku_key, "UNIVERSAL")

        # Get COGS/price
        row = conn.execute(
            "SELECT base_cost_cny, cogs_kzt FROM dim_sku WHERE sku_key = ?",
            (sku_key,)
        ).fetchone()

        if not row:
            cogs_unit = 1000.0
            price_unit = 2000.0
        else:
            # Use cogs_kzt if available, otherwise convert from CNY
            cogs_unit = row["cogs_kzt"] or (row["base_cost_cny"] or 15) * 68
            # Estimate price as 2x COGS (50% margin assumption)
            price_unit = cogs_unit * 2

    # Estimate sigma_sku
    if size_sales_history:
        total_sales_per_day = [
            sum(size_sales_history.get(s, [0])[i] for s in sizes)
            for i in range(min(90, len(next(iter(size_sales_history.values()), []))))
        ]
        if len(total_sales_per_day) > 1:
            sigma_sku = statistics.stdev(total_sales_per_day)
        else:
            sigma_sku = 2.0
    else:
        sigma_sku = 2.0

    # Generate Phase 9.6 draft
    draft = generate_po_draft(
        sku_key=sku_key,
        store_code="UNIVERSAL",
        size_sales_90d=size_sales_90d,
        size_current_stock=size_current,
        size_inbound_stock=size_inbound,
        size_sales_history=size_sales_history,
        size_stock_history=size_stock_history,
        unit_cogs=cogs_unit,
        unit_profit=price_unit - cogs_unit,
        sigma_sku=sigma_sku,
        sku_age_days=sku_age,
    )

    if draft is None:
        if verbose:
            print(f"  {sku_key}: No order needed (all sizes OK/WAIT)")
        return None

    # Get Phase 9.6 allocation
    new_allocation = {s: draft.allocations[s].order_qty_adjusted for s in draft.allocations}
    new_total = draft.total_qty

    # Calculate legacy allocation with same total
    legacy_allocation = get_legacy_allocation(size_sales_90d, new_total)

    # Calculate differences
    differences = {}
    for size in sizes:
        old_qty = legacy_allocation.get(size, 0)
        new_qty = new_allocation.get(size, 0)
        diff = new_qty - old_qty
        diff_pct = (diff / old_qty * 100) if old_qty > 0 else (100 if new_qty > 0 else 0)
        differences[size] = {
            "old_qty": old_qty,
            "new_qty": new_qty,
            "diff": diff,
            "diff_pct": diff_pct,
        }

    # Build result
    result = {
        "sku_key": sku_key,
        "total_qty": new_total,
        "should_order": draft.should_order,
        "roic": draft.roic_monthly,
        "roic_action": draft.roic_action.value,
        "trigger_sizes": ",".join(draft.trigger_sizes),
        "sku_age": sku_age,
        "sizes": differences,
        "legacy_total": sum(legacy_allocation.values()),
        "new_total": new_total,
    }

    if verbose:
        print(f"\n  {sku_key}:")
        print(f"    Total order: {new_total} units")
        print(f"    ROIC: {draft.roic_monthly:.1%} → {draft.roic_action.value}")
        print(f"    Trigger sizes: {', '.join(draft.trigger_sizes)}")
        print(f"    SKU age: {sku_age} days")
        print("    Allocation comparison:")
        for size in SIZE_ORDER:
            if size in differences:
                d = differences[size]
                sign = "+" if d["diff"] > 0 else ""
                print(f"      {size}: Old={d['old_qty']:3d}, New={d['new_qty']:3d}, Diff={sign}{d['diff']:3d} ({sign}{d['diff_pct']:.0f}%)")

    return result


def generate_comparison_report(
    sku_filter: Optional[str] = None,
    output_path: Optional[str] = None,
    verbose: bool = False
) -> list[dict]:
    """
    Generate comparison report for all (or filtered) SKUs.

    Args:
        sku_filter: Optional SKU key pattern to filter
        output_path: Optional path to save CSV report
        verbose: Show detailed output

    Returns:
        List of comparison results
    """
    with get_db() as conn:
        # Get all SKUs with size data
        query = """
            SELECT DISTINCT sku_key
            FROM dim_sku_size
            WHERE active_flag = 1
        """
        if sku_filter:
            query += f" AND sku_key LIKE '%{sku_filter}%'"
        query += " ORDER BY sku_key"

        cursor = conn.execute(query)
        sku_keys = [row[0] for row in cursor.fetchall()]

    print(f"Processing {len(sku_keys)} SKUs...")

    results = []
    for sku_key in sku_keys:
        result = compare_sku(sku_key, verbose=verbose)
        if result:
            results.append(result)

    print(f"Found {len(results)} SKUs with order recommendations")

    # Export to CSV if requested
    if output_path and results:
        export_comparison_csv(results, output_path)

    return results


def export_comparison_csv(results: list[dict], output_path: str) -> None:
    """Export comparison results to CSV."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Build rows
    rows = []
    for r in results:
        row = {
            "sku_key": r["sku_key"],
            "total_qty": r["total_qty"],
            "roic": f"{r['roic']:.1%}",
            "roic_action": r["roic_action"],
            "trigger_sizes": r["trigger_sizes"],
            "sku_age": r["sku_age"],
        }
        # Add per-size columns
        for size in SIZE_ORDER:
            if size in r["sizes"]:
                d = r["sizes"][size]
                row[f"old_{size}"] = d["old_qty"]
                row[f"new_{size}"] = d["new_qty"]
                row[f"diff_{size}"] = d["diff"]
            else:
                row[f"old_{size}"] = 0
                row[f"new_{size}"] = 0
                row[f"diff_{size}"] = 0

        rows.append(row)

    # Write CSV
    columns = ["sku_key", "total_qty", "roic", "roic_action", "trigger_sizes", "sku_age"]
    for size in SIZE_ORDER:
        columns.extend([f"old_{size}", f"new_{size}", f"diff_{size}"])

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} rows to {output_path}")


def print_summary_stats(results: list[dict]) -> None:
    """Print summary statistics for the comparison."""
    if not results:
        print("\nNo results to summarize")
        return

    # Aggregate stats
    total_orders = len(results)
    total_units = sum(r["total_qty"] for r in results)

    # ROIC distribution
    roic_full = sum(1 for r in results if r["roic_action"] == "ORDER_FULL")
    roic_flag = sum(1 for r in results if r["roic_action"] == "ORDER_WITH_FLAG")
    roic_review = sum(1 for r in results if r["roic_action"] == "REVIEW_REQUIRED")

    # Size-level differences
    size_diffs = {s: [] for s in SIZE_ORDER}
    for r in results:
        for size, d in r["sizes"].items():
            if size in size_diffs:
                size_diffs[size].append(d["diff"])

    print("\n" + "=" * 60)
    print("Comparison Summary")
    print("=" * 60)

    print(f"\nOrders: {total_orders}")
    print(f"Total units: {total_units:,}")

    print(f"\nROIC Distribution:")
    print(f"  ORDER_FULL (≥20%):       {roic_full:3d} ({100*roic_full/total_orders:.0f}%)")
    print(f"  ORDER_WITH_FLAG (10-20%): {roic_flag:3d} ({100*roic_flag/total_orders:.0f}%)")
    print(f"  REVIEW_REQUIRED (<10%):  {roic_review:3d} ({100*roic_review/total_orders:.0f}%)")

    print(f"\nAllocation Differences (New - Old) by Size:")
    for size in SIZE_ORDER:
        diffs = size_diffs.get(size, [])
        if diffs:
            total_diff = sum(diffs)
            avg_diff = total_diff / len(diffs) if diffs else 0
            sign = "+" if total_diff > 0 else ""
            print(f"  {size}: Total={sign}{total_diff:4d}, Avg={avg_diff:+.1f}")

    # Calculate total allocation shift
    total_old = 0
    total_new = 0
    for r in results:
        total_old += r.get("legacy_total", 0)
        total_new += r.get("new_total", 0)

    if total_old > 0:
        shift_pct = (total_new - total_old) / total_old * 100
        print(f"\nOverall shift: {total_new - total_old:+d} units ({shift_pct:+.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Compare legacy vs Phase 9.6 size allocation"
    )
    parser.add_argument(
        "--sku",
        type=str,
        default=None,
        help="Filter SKUs containing this string (e.g., LINE52)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output CSV path",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output per SKU",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Phase 9.6 Allocation Comparison Report")
    print("=" * 60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    # Generate report
    results = generate_comparison_report(
        sku_filter=args.sku,
        output_path=args.output,
        verbose=args.verbose
    )

    # Print summary
    print_summary_stats(results)

    print("\n" + "=" * 60)
    print("Report complete")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
