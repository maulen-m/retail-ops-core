#!/usr/bin/env python3
"""
TASK-175: Rebuild Inventory Snapshot from Stock Ledger

Rebuilds fact_inventory_snapshot_size from stock_ledger events.
Also calculates inbound_stock from pending po_line entries.

Usage:
    python scripts/rebuild_snapshot.py              # Rebuild for today
    python scripts/rebuild_snapshot.py --date 2025-12-09
    python scripts/rebuild_snapshot.py --verbose
    python scripts/rebuild_snapshot.py --compare    # Compare with existing snapshot

This script is designed to be run daily to sync the snapshot table
with the authoritative stock_ledger events.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import (
    rebuild_snapshot_from_ledger,
    get_stock_balances_all,
    get_event_summary,
)


def get_existing_snapshot(
    snapshot_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Path = None,
) -> dict:
    """
    Get existing snapshot data for comparison.

    Returns:
        Dict with {sku_id: (current_stock, inbound_stock)}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        # Note: fact_inventory_snapshot_size doesn't have store_code column
        rows = conn.execute("""
            SELECT sku_id, current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(),)).fetchall()

        return {row["sku_id"]: (row["current_stock"], row["inbound_stock"]) for row in rows}


def compare_snapshots(
    old_snapshot: dict,
    new_snapshot: dict,
) -> dict:
    """
    Compare old and new snapshots.

    Returns:
        Dict with {added: [...], removed: [...], changed: [...]}
    """
    old_skus = set(old_snapshot.keys())
    new_skus = set(new_snapshot.keys())

    added = new_skus - old_skus
    removed = old_skus - new_skus
    common = old_skus & new_skus

    changed = []
    for sku_id in common:
        old_stock, old_inbound = old_snapshot[sku_id]
        new_stock, new_inbound = new_snapshot[sku_id]
        if old_stock != new_stock or old_inbound != new_inbound:
            changed.append({
                "sku_id": sku_id,
                "old_stock": old_stock,
                "new_stock": new_stock,
                "old_inbound": old_inbound,
                "new_inbound": new_inbound,
            })

    return {
        "added": list(added),
        "removed": list(removed),
        "changed": changed,
    }


def rebuild_snapshot(
    snapshot_date: date = None,
    store_code: str = "UNIVERSAL",
    verbose: bool = False,
    compare: bool = False,
    db_path: Path = None,
) -> dict:
    """
    Rebuild snapshot from ledger.

    Args:
        snapshot_date: Date for snapshot (default: today)
        store_code: Store code (default: UNIVERSAL)
        verbose: Print detailed output
        compare: Compare with existing snapshot before overwriting
        db_path: Database path

    Returns:
        Dict with results
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    print(f"\n{'=' * 60}")
    print(f"Rebuild Inventory Snapshot")
    print(f"{'=' * 60}")
    print(f"Date:    {snapshot_date}")
    print(f"Store:   {store_code}")

    # Get event summary
    event_summary = get_event_summary(as_of_date=snapshot_date, store_code=store_code, db_path=db_path)

    print(f"\nLedger Events (as of {snapshot_date}):")
    total_events = 0
    for event_type, stats in sorted(event_summary.items()):
        print(f"  {event_type:12}: {stats['count']:4} events, {stats['qty_total']:+6} units")
        total_events += stats["count"]

    if total_events == 0:
        print("\nWARNING: No ledger events found. Nothing to rebuild.")
        return {"rows_created": 0, "total_units": 0}

    # Get existing snapshot for comparison
    old_snapshot = {}
    if compare:
        old_snapshot = get_existing_snapshot(snapshot_date, store_code, db_path)
        print(f"\nExisting snapshot: {len(old_snapshot)} SKUs")

    # Rebuild snapshot
    print(f"\nRebuilding snapshot...")
    rows_created = rebuild_snapshot_from_ledger(
        snapshot_date=snapshot_date,
        store_code=store_code,
        db_path=db_path,
    )

    # Get new snapshot for summary
    with get_db(db_path) as conn:
        # Total current stock
        current_total = conn.execute("""
            SELECT COALESCE(SUM(current_stock), 0) as total
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(),)).fetchone()["total"]

        # Total inbound stock
        inbound_total = conn.execute("""
            SELECT COALESCE(SUM(inbound_stock), 0) as total
            FROM fact_inventory_snapshot_size
            WHERE snapshot_date = ?
        """, (snapshot_date.isoformat(),)).fetchone()["total"]

    # Compare if requested
    if compare and old_snapshot:
        new_snapshot = get_existing_snapshot(snapshot_date, store_code, db_path)
        diff = compare_snapshots(old_snapshot, new_snapshot)

        if diff["added"] or diff["removed"] or diff["changed"]:
            print(f"\nChanges detected:")
            if diff["added"]:
                print(f"  Added:   {len(diff['added'])} SKUs")
                if verbose:
                    for sku_id in diff["added"][:5]:
                        print(f"    - {sku_id}")
                    if len(diff["added"]) > 5:
                        print(f"    ... and {len(diff['added']) - 5} more")

            if diff["removed"]:
                print(f"  Removed: {len(diff['removed'])} SKUs")
                if verbose:
                    for sku_id in diff["removed"][:5]:
                        print(f"    - {sku_id}")

            if diff["changed"]:
                print(f"  Changed: {len(diff['changed'])} SKUs")
                if verbose:
                    for change in diff["changed"][:5]:
                        print(f"    - {change['sku_id']}: "
                              f"stock {change['old_stock']} → {change['new_stock']}, "
                              f"inbound {change['old_inbound']} → {change['new_inbound']}")
        else:
            print(f"\nNo changes detected (snapshot unchanged)")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"Snapshot rows created: {rows_created}")
    print(f"Total current stock:   {current_total}")
    print(f"Total inbound stock:   {inbound_total}")
    print(f"Total stock (current + inbound): {current_total + inbound_total}")

    return {
        "rows_created": rows_created,
        "current_stock_total": current_total,
        "inbound_stock_total": inbound_total,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild fact_inventory_snapshot_size from stock_ledger"
    )
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
        help="Snapshot date (default: today)",
    )
    parser.add_argument(
        "--store",
        default="UNIVERSAL",
        help="Store code (default: UNIVERSAL)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output",
    )
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Compare with existing snapshot before rebuilding",
    )

    args = parser.parse_args()

    result = rebuild_snapshot(
        snapshot_date=args.date,
        store_code=args.store,
        verbose=args.verbose,
        compare=args.compare,
    )

    print("\nRebuild complete!")


if __name__ == "__main__":
    main()
