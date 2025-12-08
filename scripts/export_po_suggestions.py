#!/usr/bin/env python3
"""
Export PO Suggestions: Generate size-split PO recommendations CSV.

TASK-167: Phase 9.6 Update - Size-Aware Allocation Export

This script:
1. Reads SKU metrics from fact_sku_metrics
2. Gets size mix from historical sales (fact_sales_daily_size)
3. Calculates size-split allocation for suggested order quantities
4. Uses Phase 9.6 size-aware allocation when --size-aware flag is set
5. Exports to CSV with columns for each size

Output columns:
- store_code, sku_key, status
- total_qty (suggested order)
- size_S, size_M, size_L, size_XL, size_2XL, size_3XL, size_4XL (size split)
- unit_cost, on_hand, on_order, rop, roic_pct, d30
- Phase 9.6 only: trigger_sizes, roic_action, demand_confidence

Usage:
    python scripts/export_po_suggestions.py                      # Export all REORDER SKUs (legacy mode)
    python scripts/export_po_suggestions.py --all                # Export all SKUs (legacy mode)
    python scripts/export_po_suggestions.py --output exports/po.csv
    python scripts/export_po_suggestions.py --dry-run            # Preview without saving
    python scripts/export_po_suggestions.py --size-aware         # Use Phase 9.6 size-aware allocation
    python scripts/export_po_suggestions.py --size-aware --quiet # Size-aware with minimal output
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db

# Phase 9.6 imports
try:
    from core.automation.po_generator import generate_po_draft_size_aware
    from core.calc.size_allocation import PODraft, ROICAction, DemandConfidence
    PHASE_96_AVAILABLE = True
except ImportError:
    PHASE_96_AVAILABLE = False


# Standard size order for output columns
SIZE_ORDER = ["S", "M", "L", "XL", "2XL", "3XL", "4XL"]


def get_sku_metrics(conn, reorder_only: bool = True) -> list[dict]:
    """
    Get SKU metrics from fact_sku_metrics.

    Args:
        conn: Database connection
        reorder_only: If True, only return REORDER status SKUs

    Returns:
        List of SKU metric dicts
    """
    # Get latest computed_at timestamp
    cursor = conn.execute(
        "SELECT MAX(computed_at) FROM fact_sku_metrics"
    )
    latest = cursor.fetchone()[0]

    if not latest:
        return []

    where_clause = "WHERE computed_at = ?"
    params = [latest]

    if reorder_only:
        where_clause += " AND status = 'REORDER'"

    cursor = conn.execute(
        f"""
        SELECT
            sku_key, store_code, d30, ss_total, rop, target_stock,
            current_stock, inbound_stock, total_stock,
            status, suggested_order_qty, roic_monthly, avg_cogs
        FROM fact_sku_metrics
        {where_clause}
        ORDER BY roic_monthly DESC
        """,
        params
    )

    columns = [
        "sku_key", "store_code", "d30", "ss_total", "rop", "target_stock",
        "current_stock", "inbound_stock", "total_stock",
        "status", "suggested_order_qty", "roic_monthly", "avg_cogs"
    ]

    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_size_mix(conn, sku_key: str, days: int = 90) -> dict[str, float]:
    """
    Get historical size mix for a SKU from sales data.

    Args:
        conn: Database connection
        sku_key: SKU key
        days: Number of days to look back

    Returns:
        Dict of {size: proportion} where proportions sum to 1.0
    """
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    cursor = conn.execute(
        """
        SELECT
            ds.my_size,
            SUM(fds.units) as total_units
        FROM fact_sales_daily_size fds
        JOIN dim_sku_size ds ON fds.sku_id = ds.sku_id
        WHERE ds.sku_key = ? AND fds.sale_date >= ?
        GROUP BY ds.my_size
        """,
        (sku_key, cutoff)
    )

    size_units = {}
    total = 0
    for row in cursor.fetchall():
        size, units = row
        size_units[size] = units
        total += units

    if total == 0:
        # Default to equal distribution
        return {s: 1.0 / len(SIZE_ORDER) for s in SIZE_ORDER}

    # Convert to proportions
    return {size: units / total for size, units in size_units.items()}


def get_size_mix_from_inventory(conn, sku_key: str) -> dict[str, float]:
    """
    Get size mix from current inventory snapshot (fallback).

    Args:
        conn: Database connection
        sku_key: SKU key

    Returns:
        Dict of {size: proportion}
    """
    cursor = conn.execute(
        """
        SELECT
            my_size,
            current_stock
        FROM fact_inventory_snapshot_size
        WHERE sku_key = ? AND snapshot_date = (
            SELECT MAX(snapshot_date) FROM fact_inventory_snapshot_size
        )
        """,
        (sku_key,)
    )

    size_units = {}
    total = 0
    for row in cursor.fetchall():
        size, stock = row
        size_units[size] = stock or 0
        total += stock or 0

    if total == 0:
        return {s: 1.0 / len(SIZE_ORDER) for s in SIZE_ORDER}

    return {size: units / total for size, units in size_units.items()}


def allocate_sizes(total_qty: int, size_mix: dict[str, float]) -> dict[str, int]:
    """
    Allocate total quantity across sizes based on mix proportions.

    Uses largest remainder method for integer allocation.

    Args:
        total_qty: Total quantity to allocate
        size_mix: Dict of {size: proportion}

    Returns:
        Dict of {size: quantity}
    """
    if total_qty <= 0:
        return {s: 0 for s in SIZE_ORDER}

    # Calculate initial allocation (floor)
    allocation = {}
    remainders = {}

    for size in SIZE_ORDER:
        prop = size_mix.get(size, 0)
        exact = total_qty * prop
        floor_val = int(exact)
        allocation[size] = floor_val
        remainders[size] = exact - floor_val

    # Distribute remaining units to sizes with largest remainders
    allocated = sum(allocation.values())
    remaining = total_qty - allocated

    # Sort sizes by remainder descending
    sorted_sizes = sorted(remainders.keys(), key=lambda s: -remainders[s])

    for i in range(remaining):
        size = sorted_sizes[i % len(sorted_sizes)]
        allocation[size] += 1

    return allocation


def get_unit_cost(conn, sku_key: str) -> float:
    """Get unit cost (COGS) for SKU from dim_sku or metrics."""
    # Try dim_sku first
    cursor = conn.execute(
        "SELECT base_cost_cny FROM dim_sku WHERE sku_key = ?",
        (sku_key,)
    )
    row = cursor.fetchone()
    if row and row[0]:
        # Approximate conversion CNY to KZT (rough estimate)
        return row[0] * 68  # ~68 KZT per CNY

    # Fallback to avg_cogs from metrics
    cursor = conn.execute(
        """
        SELECT avg_cogs FROM fact_sku_metrics
        WHERE sku_key = ? AND computed_at = (
            SELECT MAX(computed_at) FROM fact_sku_metrics
        )
        """,
        (sku_key,)
    )
    row = cursor.fetchone()
    return row[0] if row else 0


def generate_po_suggestions(
    conn,
    reorder_only: bool = True,
    verbose: bool = True,
) -> list[dict]:
    """
    Generate PO suggestion records with size splits.

    Returns:
        List of dicts with PO suggestion data
    """
    skus = get_sku_metrics(conn, reorder_only=reorder_only)

    if verbose:
        print(f"Found {len(skus)} SKUs to process")

    results = []

    for sku in skus:
        sku_key = sku["sku_key"]
        total_qty = sku["suggested_order_qty"]

        # Get size mix (try sales first, then inventory)
        size_mix = get_size_mix(conn, sku_key)
        if sum(size_mix.values()) == 0:
            size_mix = get_size_mix_from_inventory(conn, sku_key)

        # Allocate across sizes
        size_allocation = allocate_sizes(total_qty, size_mix)

        # Get unit cost
        unit_cost = get_unit_cost(conn, sku_key)

        record = {
            "store_code": sku["store_code"],
            "sku_key": sku_key,
            "status": sku["status"],
            "total_qty": total_qty,
            **{f"size_{s}": size_allocation.get(s, 0) for s in SIZE_ORDER},
            "unit_cost": round(unit_cost, 2),
            "on_hand": sku["current_stock"],
            "on_order": sku["inbound_stock"],
            "rop": round(sku["rop"], 0),
            "roic_pct": round(sku["roic_monthly"], 1),
            "d30": round(sku["d30"], 2),
            # Phase 9.6 columns (empty for legacy mode)
            "trigger_sizes": "",
            "roic_action": "",
            "demand_confidence": "",
        }
        results.append(record)

    return results


def generate_po_suggestions_size_aware(
    conn,
    verbose: bool = True,
) -> list[dict]:
    """
    Generate PO suggestion records using Phase 9.6 size-aware allocation.

    TASK-167: New function that uses generate_po_draft_size_aware().

    Returns:
        List of dicts with PO suggestion data including Phase 9.6 columns
    """
    if not PHASE_96_AVAILABLE:
        print("ERROR: Phase 9.6 modules not available")
        return []

    # Get all active SKUs with size-level data
    cursor = conn.execute("""
        SELECT DISTINCT sku_key
        FROM dim_sku_size
        WHERE active_flag = 1
        ORDER BY sku_key
    """)

    sku_keys = [row[0] for row in cursor.fetchall()]

    if verbose:
        print(f"Found {len(sku_keys)} SKUs with size-level data")

    results = []

    for sku_key in sku_keys:
        if verbose:
            print(f"  Processing {sku_key}...", end=" ")

        try:
            draft = generate_po_draft_size_aware(sku_key, "UNIVERSAL")
        except Exception as e:
            if verbose:
                print(f"ERROR: {e}")
            continue

        if draft is None:
            if verbose:
                print("SKIP (no data)")
            continue

        if not draft.should_order:
            if verbose:
                print("OK (no order needed)")
            continue

        # Build size allocation from draft
        size_allocation = {
            s: draft.allocations.get(s, None)
            for s in SIZE_ORDER
        }
        size_qtys = {
            f"size_{s}": (a.order_qty_adjusted if a else 0)
            for s, a in size_allocation.items()
        }

        record = {
            "store_code": draft.store_code,
            "sku_key": draft.sku_key,
            "status": "REORDER" if draft.should_order else "OK",
            "total_qty": draft.total_qty,
            **size_qtys,
            "unit_cost": round(draft.cogs_unit, 2),
            "on_hand": draft.current_stock_total,
            "on_order": draft.inbound_stock_total,
            "rop": round(draft.rop_sku, 0),
            "roic_pct": round(draft.roic_monthly * 100, 1),
            "d30": round(draft.d_sku * 30, 2),
            # Phase 9.6 columns
            "trigger_sizes": ",".join(draft.trigger_sizes),
            "roic_action": draft.roic_action.value,
            "demand_confidence": draft.demand_confidence.value,
        }
        results.append(record)

        if verbose:
            print(f"ORDER {draft.total_qty} ({draft.roic_action.value})")

    return results


def export_to_csv(records: list[dict], filepath: str, include_phase96: bool = False) -> int:
    """
    Export records to CSV file.

    Args:
        records: List of record dicts
        filepath: Output CSV path
        include_phase96: Include Phase 9.6 columns

    Returns:
        Number of records written.
    """
    if not records:
        return 0

    # Ensure directory exists
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    # Define column order
    columns = [
        "store_code", "sku_key", "status", "total_qty",
        *[f"size_{s}" for s in SIZE_ORDER],
        "unit_cost", "on_hand", "on_order", "rop", "roic_pct", "d30"
    ]

    # Add Phase 9.6 columns if requested
    if include_phase96:
        columns.extend(["trigger_sizes", "roic_action", "demand_confidence"])

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)

    return len(records)


def main():
    parser = argparse.ArgumentParser(
        description="Export PO suggestions with size splits to CSV"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output CSV path (default: exports/YYYY-MM-DD/po_suggestions.csv)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export all SKUs, not just REORDER status",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    parser.add_argument(
        "--size-aware",
        action="store_true",
        help="Use Phase 9.6 size-aware allocation (requires Phase 9.6 modules)",
    )

    args = parser.parse_args()

    # Default output path
    if args.output is None:
        today = datetime.now().strftime("%Y-%m-%d")
        args.output = f"exports/{today}/po_suggestions.csv"

    print("=" * 60)
    print("Export PO Suggestions")
    if getattr(args, 'size_aware', False):
        print("Mode: Phase 9.6 Size-Aware Allocation")
    else:
        print("Mode: Legacy (historical mix)")
    print("=" * 60)

    # Check Phase 9.6 availability if requested
    use_size_aware = getattr(args, 'size_aware', False)
    if use_size_aware and not PHASE_96_AVAILABLE:
        print("\nERROR: Phase 9.6 modules not available.")
        print("Install with: pip install -e . or check core/calc/size_allocation.py")
        return 1

    # Generate records
    with get_db() as conn:
        if use_size_aware:
            records = generate_po_suggestions_size_aware(
                conn,
                verbose=not args.quiet,
            )
        else:
            records = generate_po_suggestions(
                conn,
                reorder_only=not args.all,
                verbose=not args.quiet,
            )

    if not records:
        print("\nNo records to export")
        return 0

    if not args.quiet:
        print(f"\nGenerated {len(records)} PO suggestions")
        print("\nSample (first 3):")
        for r in records[:3]:
            sizes = [f"{s}:{r.get(f'size_{s}', 0)}" for s in SIZE_ORDER if r.get(f'size_{s}', 0) > 0]
            print(f"  {r['sku_key']}: {r['total_qty']} units -> {', '.join(sizes)}")

    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - no file written")
        print("=" * 60)
        return 0

    # Export
    count = export_to_csv(records, args.output, include_phase96=use_size_aware)

    print("\n" + "=" * 60)
    print(f"Exported {count} records to {args.output}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
