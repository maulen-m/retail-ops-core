#!/usr/bin/env python3
"""
TASK-187: Ledger Validation Script (Phase 10)

Validates stock ledger data integrity:
1. Check stock balances match sum of events
2. Detect orphan events (no matching SKU in dim_sku_size)
3. Validate event types
4. Check for duplicate events
5. Verify snapshot consistency with ledger
6. Check PO line received_qty vs INBOUND events

Usage:
    python scripts/validate_ledger.py              # Full validation
    python scripts/validate_ledger.py --fix        # Fix detectable issues
    python scripts/validate_ledger.py --verbose    # Show details
"""

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import (
    get_stock_balances_all,
    get_event_summary,
    VALID_EVENT_TYPES,
)


def check_balance_consistency(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 1: Verify stock balances match sum of ledger events.

    Returns dict with {valid: bool, mismatches: list}
    """
    result = {"valid": True, "mismatches": [], "sku_count": 0}

    with get_db(db_path) as conn:
        # Get all balances from ledger events
        ledger_balances = conn.execute("""
            SELECT sku_id, store_code, SUM(qty_change) as balance
            FROM stock_ledger
            GROUP BY sku_id, store_code
        """).fetchall()

        result["sku_count"] = len(ledger_balances)

        # Check if fact_stock_snapshot exists
        table_exists = conn.execute("""
            SELECT COUNT(*) as count FROM sqlite_master
            WHERE type='table' AND name='fact_stock_snapshot'
        """).fetchone()["count"]

        if not table_exists:
            result["skipped"] = True
            result["reason"] = "fact_stock_snapshot table not found"
            if verbose:
                print("  Skipped: fact_stock_snapshot table not found")
            return result

        # Get snapshot balances
        snapshot_balances = {}
        snapshot_rows = conn.execute("""
            SELECT sku_id, store_code, current_stock
            FROM fact_stock_snapshot
        """).fetchall()

        for row in snapshot_rows:
            key = (row["sku_id"], row["store_code"])
            snapshot_balances[key] = row["current_stock"]

        # Compare
        for row in ledger_balances:
            key = (row["sku_id"], row["store_code"])
            ledger_balance = row["balance"]
            snapshot_balance = snapshot_balances.get(key, 0)

            if ledger_balance != snapshot_balance:
                result["valid"] = False
                result["mismatches"].append({
                    "sku_id": row["sku_id"],
                    "store_code": row["store_code"],
                    "ledger_balance": ledger_balance,
                    "snapshot_balance": snapshot_balance,
                    "diff": ledger_balance - snapshot_balance,
                })

    if verbose:
        print(f"  Checked {result['sku_count']} SKUs")
        if result["mismatches"]:
            print(f"  Found {len(result['mismatches'])} mismatches:")
            for m in result["mismatches"][:5]:
                print(f"    {m['sku_id']}: ledger={m['ledger_balance']}, snapshot={m['snapshot_balance']}")
            if len(result["mismatches"]) > 5:
                print(f"    ... and {len(result['mismatches']) - 5} more")

    return result


def check_orphan_events(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 2: Find events with no matching SKU in dim_sku_size.

    Returns dict with {valid: bool, orphans: list}
    """
    result = {"valid": True, "orphans": []}

    with get_db(db_path) as conn:
        orphans = conn.execute("""
            SELECT DISTINCT sl.sku_id, sl.event_type, COUNT(*) as event_count
            FROM stock_ledger sl
            LEFT JOIN dim_sku_size dss ON sl.sku_id = dss.sku_id
            WHERE dss.sku_id IS NULL
            GROUP BY sl.sku_id, sl.event_type
        """).fetchall()

        for row in orphans:
            result["orphans"].append({
                "sku_id": row["sku_id"],
                "event_type": row["event_type"],
                "count": row["event_count"],
            })

    if result["orphans"]:
        result["valid"] = False

    if verbose:
        if result["orphans"]:
            print(f"  Found {len(result['orphans'])} orphan SKU groups:")
            for o in result["orphans"][:5]:
                print(f"    {o['sku_id']}: {o['count']} {o['event_type']} events")
            if len(result["orphans"]) > 5:
                print(f"    ... and {len(result['orphans']) - 5} more")
        else:
            print("  No orphan events found")

    return result


def check_event_types(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 3: Verify all events have valid event types.

    Returns dict with {valid: bool, invalid: list}
    """
    result = {"valid": True, "invalid": []}

    with get_db(db_path) as conn:
        invalid = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM stock_ledger
            WHERE event_type NOT IN (?, ?, ?, ?, ?, ?)
            GROUP BY event_type
        """, tuple(VALID_EVENT_TYPES)).fetchall()

        for row in invalid:
            result["invalid"].append({
                "event_type": row["event_type"],
                "count": row["count"],
            })

    if result["invalid"]:
        result["valid"] = False

    if verbose:
        if result["invalid"]:
            print(f"  Found {len(result['invalid'])} invalid event types:")
            for i in result["invalid"]:
                print(f"    '{i['event_type']}': {i['count']} events")
        else:
            print(f"  All events have valid types: {', '.join(VALID_EVENT_TYPES)}")

    return result


def check_duplicate_events(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 4: Find potential duplicate events.

    Duplicates are events with same (sku_id, event_type, qty_change, event_date, reference_id)
    """
    result = {"valid": True, "duplicates": []}

    with get_db(db_path) as conn:
        duplicates = conn.execute("""
            SELECT
                sku_id, event_type, qty_change, event_date, reference_id,
                COUNT(*) as count
            FROM stock_ledger
            GROUP BY sku_id, event_type, qty_change, event_date, reference_id
            HAVING COUNT(*) > 1
        """).fetchall()

        for row in duplicates:
            result["duplicates"].append({
                "sku_id": row["sku_id"],
                "event_type": row["event_type"],
                "qty_change": row["qty_change"],
                "event_date": row["event_date"],
                "reference_id": row["reference_id"],
                "count": row["count"],
            })

    if result["duplicates"]:
        result["valid"] = False

    if verbose:
        if result["duplicates"]:
            print(f"  Found {len(result['duplicates'])} potential duplicate groups:")
            for d in result["duplicates"][:5]:
                print(f"    {d['sku_id']} {d['event_type']}: {d['count']}x on {d['event_date']}")
            if len(result["duplicates"]) > 5:
                print(f"    ... and {len(result['duplicates']) - 5} more")
        else:
            print("  No duplicate events found")

    return result


def check_po_inbound_consistency(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 5: Verify PO received_qty matches INBOUND events.

    Returns dict with {valid: bool, mismatches: list}
    """
    result = {"valid": True, "mismatches": [], "po_count": 0}

    with get_db(db_path) as conn:
        # Get PO lines with received quantities
        po_lines = conn.execute("""
            SELECT
                pl.po_id, pl.sku_id,
                pl.received_qty,
                (SELECT COALESCE(SUM(qty_change), 0)
                 FROM stock_ledger sl
                 WHERE sl.reference_id = pl.po_id
                   AND sl.sku_id = pl.sku_id
                   AND sl.event_type = 'INBOUND'
                   AND sl.reference_type = 'PO') as ledger_qty
            FROM po_line pl
            WHERE pl.received_qty > 0
        """).fetchall()

        result["po_count"] = len(po_lines)

        for row in po_lines:
            if row["received_qty"] != row["ledger_qty"]:
                result["valid"] = False
                result["mismatches"].append({
                    "po_id": row["po_id"],
                    "sku_id": row["sku_id"],
                    "received_qty": row["received_qty"],
                    "ledger_qty": row["ledger_qty"],
                    "diff": row["received_qty"] - row["ledger_qty"],
                })

    if verbose:
        print(f"  Checked {result['po_count']} PO lines")
        if result["mismatches"]:
            print(f"  Found {len(result['mismatches'])} mismatches:")
            for m in result["mismatches"][:5]:
                print(f"    {m['po_id']} {m['sku_id']}: received={m['received_qty']}, ledger={m['ledger_qty']}")
            if len(result["mismatches"]) > 5:
                print(f"    ... and {len(result['mismatches']) - 5} more")
        else:
            print("  All PO INBOUND events match")

    return result


def check_sales_consistency(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 6: Verify sales_fact_v2 records have corresponding SALE events.

    Returns dict with {valid: bool, missing: int}
    """
    result = {"valid": True, "missing": 0, "sales_count": 0}

    with get_db(db_path) as conn:
        # Count sales records
        sales_count = conn.execute("""
            SELECT COUNT(*) as count FROM sales_fact_v2
        """).fetchone()["count"]
        result["sales_count"] = sales_count

        # Find sales without ledger events
        missing = conn.execute("""
            SELECT COUNT(*) as count
            FROM sales_fact_v2 sf
            WHERE NOT EXISTS (
                SELECT 1 FROM stock_ledger sl
                WHERE sl.reference_id = sf.order_id
                  AND sl.sku_id = sf.sku_id
                  AND sl.event_type = 'SALE'
            )
        """).fetchone()["count"]

        result["missing"] = missing
        if missing > 0:
            result["valid"] = False

    if verbose:
        print(f"  Sales records: {result['sales_count']}")
        if result["missing"] > 0:
            print(f"  Missing SALE events: {result['missing']}")
        else:
            print("  All sales have ledger events")

    return result


def check_negative_balances(
    db_path: Path,
    verbose: bool = False,
) -> dict:
    """
    Check 7: Find SKUs with negative stock balance.

    Returns dict with {count: int, skus: list}
    """
    result = {"count": 0, "skus": []}

    with get_db(db_path) as conn:
        negative = conn.execute("""
            SELECT sku_id, store_code, SUM(qty_change) as balance
            FROM stock_ledger
            GROUP BY sku_id, store_code
            HAVING SUM(qty_change) < 0
        """).fetchall()

        for row in negative:
            result["skus"].append({
                "sku_id": row["sku_id"],
                "store_code": row["store_code"],
                "balance": row["balance"],
            })
        result["count"] = len(negative)

    if verbose:
        if result["skus"]:
            print(f"  Found {result['count']} SKUs with negative balance:")
            for s in result["skus"][:5]:
                print(f"    {s['sku_id']} ({s['store_code']}): {s['balance']}")
            if result["count"] > 5:
                print(f"    ... and {result['count'] - 5} more")
        else:
            print("  No negative balances")

    return result


def fix_snapshot_mismatches(
    db_path: Path,
    verbose: bool = False,
) -> int:
    """
    Fix snapshot mismatches by rebuilding from ledger events.

    Returns number of rows fixed.
    """
    from core.db.ledger import rebuild_snapshot_from_ledger

    result = rebuild_snapshot_from_ledger(db_path=db_path)
    return result["sku_count"]


def run_validation(
    db_path: Optional[Path] = None,
    fix: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Run all validation checks.

    Args:
        db_path: Database path
        fix: Whether to attempt fixes
        verbose: Print details

    Returns:
        Dict with results from all checks
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    results = {
        "database": str(db_path),
        "timestamp": date.today().isoformat(),
        "checks": {},
        "all_valid": True,
    }

    checks = [
        ("balance_consistency", check_balance_consistency),
        ("orphan_events", check_orphan_events),
        ("event_types", check_event_types),
        ("duplicate_events", check_duplicate_events),
        ("po_inbound_consistency", check_po_inbound_consistency),
        ("sales_consistency", check_sales_consistency),
        ("negative_balances", check_negative_balances),
    ]

    for name, check_func in checks:
        if verbose:
            print(f"\n[{name.upper()}]")

        try:
            result = check_func(db_path, verbose)
            results["checks"][name] = result

            # Skipped checks don't affect overall validity
            if result.get("skipped"):
                pass
            elif name != "negative_balances" and not result.get("valid", True):
                results["all_valid"] = False
        except Exception as e:
            results["checks"][name] = {"error": str(e)}
            results["all_valid"] = False
            if verbose:
                print(f"  ERROR: {e}")

    # Apply fixes if requested
    if fix and not results["all_valid"]:
        if verbose:
            print("\n[APPLYING FIXES]")

        # Fix snapshot mismatches
        if not results["checks"].get("balance_consistency", {}).get("valid", True):
            fixed = fix_snapshot_mismatches(db_path, verbose)
            results["fixes"] = {"snapshot_rebuilt": fixed}
            if verbose:
                print(f"  Rebuilt snapshot for {fixed} SKUs")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate stock ledger data integrity"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to fix detectable issues",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show summary",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Stock Ledger Validation")
    print("=" * 60)

    verbose = not args.quiet
    results = run_validation(
        fix=args.fix,
        verbose=verbose,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("-" * 60)

    for name, check_result in results["checks"].items():
        if check_result.get("error"):
            status = "ERROR"
        elif check_result.get("skipped"):
            status = "SKIP"
        elif name == "negative_balances":
            count = check_result.get("count", 0)
            status = f"WARN ({count})" if count > 0 else "OK"
        elif check_result.get("valid", True):
            status = "OK"
        else:
            status = "FAIL"

        print(f"  {name}: {status}")

    print("-" * 60)
    print(f"Overall: {'PASS' if results['all_valid'] else 'FAIL'}")

    if results.get("fixes"):
        print(f"Fixes applied: {results['fixes']}")

    print("=" * 60)

    return 0 if results["all_valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
