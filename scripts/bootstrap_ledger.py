#!/usr/bin/env python3
"""
TASK-174: Bootstrap Stock Ledger from Excel Snapshot

Reads an inventory snapshot Excel file and creates INITIAL events
in the stock_ledger table for each SKU/size combination.

Usage:
    python scripts/bootstrap_ledger.py excel/Current_stock_2025-12-09.xlsx --date 2025-12-09
    python scripts/bootstrap_ledger.py --dry-run
    python scripts/bootstrap_ledger.py --verbose

Expected Excel columns:
    - SKU_ID (size-level identifier)
    - SKU_key (style-level identifier)
    - MY_SIZE (size label)
    - Current_stock (opening balance)

Idempotency:
    Running this script multiple times with the same date will NOT
    duplicate events. It checks for existing INITIAL events for each SKU
    on the specified date and skips them.
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event, count_ledger_events, get_stock_balance


def parse_bootstrap_excel(
    xlsx_path: str,
    sheet_name: str = 0,
) -> list[dict]:
    """
    Parse inventory snapshot Excel file.

    Args:
        xlsx_path: Path to Excel file
        sheet_name: Sheet name or index (default: 0, first sheet)

    Returns:
        List of dicts with SKU_ID, SKU_key, MY_SIZE, Current_stock
    """
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)

    # Normalize column names (handle case variations)
    col_map = {}
    for col in df.columns:
        col_lower = col.lower().replace(" ", "_").replace("-", "_")
        if col_lower in ["sku_id", "skuid"]:
            col_map[col] = "sku_id"
        elif col_lower in ["sku_key", "skukey"]:
            col_map[col] = "sku_key"
        elif col_lower in ["my_size", "mysize", "size"]:
            if "sku_id" not in col_map.values():  # Skip duplicate MY_SIZE columns
                col_map[col] = "my_size"
            elif "my_size" not in col_map.values():
                col_map[col] = "my_size"
        elif col_lower in ["current_stock", "currentstock", "stock", "qty"]:
            col_map[col] = "current_stock"

    # Rename columns
    df = df.rename(columns=col_map)

    # Validate required columns
    required = ["sku_id", "sku_key", "my_size", "current_stock"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    # Convert to list of dicts
    records = []
    for _, row in df.iterrows():
        sku_id = str(row["sku_id"]).strip()
        sku_key = str(row["sku_key"]).strip()
        my_size = str(row["my_size"]).strip()

        # Handle NaN/None stock values
        stock = row["current_stock"]
        if pd.isna(stock):
            stock = 0
        else:
            stock = int(stock)

        # Skip rows with empty SKU_ID
        if not sku_id or sku_id.lower() == "nan":
            continue

        records.append({
            "sku_id": sku_id,
            "sku_key": sku_key,
            "my_size": my_size,
            "current_stock": stock,
        })

    return records


def bootstrap_ledger(
    xlsx_path: str,
    bootstrap_date: date = None,
    store_code: str = "UNIVERSAL",
    dry_run: bool = False,
    verbose: bool = False,
    db_path: Path = None,
) -> dict:
    """
    Bootstrap stock_ledger from Excel inventory snapshot.

    Creates INITIAL events for each SKU/size with current_stock > 0.
    Idempotent: skips SKUs that already have INITIAL events for this date.

    Args:
        xlsx_path: Path to inventory Excel file
        bootstrap_date: Date for INITIAL events (default: today)
        store_code: Store code (default: UNIVERSAL)
        dry_run: If True, don't write to DB
        verbose: If True, print each SKU processed
        db_path: Database path (default: DEFAULT_DB_PATH)

    Returns:
        Dict with counts: {inserted, skipped, total_units, errors}
    """
    if bootstrap_date is None:
        bootstrap_date = date.today()

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    print(f"\n{'=' * 60}")
    print(f"Bootstrap Stock Ledger")
    print(f"{'=' * 60}")
    print(f"Source:  {xlsx_path}")
    print(f"Date:    {bootstrap_date}")
    print(f"Store:   {store_code}")
    print(f"Dry run: {dry_run}")

    # Parse Excel
    records = parse_bootstrap_excel(xlsx_path)
    print(f"Records: {len(records)} rows parsed")

    # Track results
    result = {
        "inserted": 0,
        "skipped": 0,
        "skipped_zero": 0,
        "total_units": 0,
        "errors": [],
    }

    with get_db(db_path) as conn:
        for rec in records:
            sku_id = rec["sku_id"]
            sku_key = rec["sku_key"]
            my_size = rec["my_size"]
            stock = rec["current_stock"]

            # Skip zero stock (no need for INITIAL event)
            if stock == 0:
                result["skipped_zero"] += 1
                if verbose:
                    print(f"  SKIP (zero): {sku_id}")
                continue

            # Check for existing INITIAL event (idempotency)
            existing = conn.execute("""
                SELECT ledger_id FROM stock_ledger
                WHERE sku_id = ?
                  AND store_code = ?
                  AND event_type = 'INITIAL'
                  AND event_date = ?
            """, (sku_id, store_code, bootstrap_date.isoformat())).fetchone()

            if existing:
                result["skipped"] += 1
                if verbose:
                    print(f"  SKIP (exists): {sku_id} - ledger_id={existing['ledger_id']}")
                continue

            # Insert INITIAL event
            if not dry_run:
                try:
                    add_ledger_event(
                        event_type="INITIAL",
                        sku_id=sku_id,
                        sku_key=sku_key,
                        my_size=my_size,
                        qty_change=stock,
                        event_date=bootstrap_date,
                        store_code=store_code,
                        notes=f"Bootstrap from {Path(xlsx_path).name}",
                        input_source="IMPORT",
                        created_by="bootstrap_ledger",
                        db_path=db_path,
                    )
                    result["inserted"] += 1
                    result["total_units"] += stock
                    if verbose:
                        print(f"  INSERT: {sku_id} = {stock} units")
                except Exception as e:
                    result["errors"].append(f"{sku_id}: {str(e)}")
                    if verbose:
                        print(f"  ERROR: {sku_id} - {e}")
            else:
                result["inserted"] += 1
                result["total_units"] += stock
                if verbose:
                    print(f"  DRY RUN: {sku_id} = {stock} units")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"INITIAL events inserted:  {result['inserted']}")
    print(f"Skipped (already exists): {result['skipped']}")
    print(f"Skipped (zero stock):     {result['skipped_zero']}")
    print(f"Total units bootstrapped: {result['total_units']}")

    if result["errors"]:
        print(f"\nERRORS ({len(result['errors'])}):")
        for err in result["errors"][:10]:
            print(f"  - {err}")
        if len(result["errors"]) > 10:
            print(f"  ... and {len(result['errors']) - 10} more")

    return result


def verify_bootstrap(
    bootstrap_date: date,
    store_code: str = "UNIVERSAL",
    db_path: Path = None,
) -> dict:
    """
    Verify bootstrap by checking INITIAL event totals.

    Args:
        bootstrap_date: Date to check
        store_code: Store code
        db_path: Database path

    Returns:
        Dict with verification results
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    with get_db(db_path) as conn:
        # Count INITIAL events
        initial_count = conn.execute("""
            SELECT COUNT(*) as cnt
            FROM stock_ledger
            WHERE event_type = 'INITIAL'
              AND store_code = ?
              AND event_date = ?
        """, (store_code, bootstrap_date.isoformat())).fetchone()["cnt"]

        # Sum INITIAL units
        initial_sum = conn.execute("""
            SELECT COALESCE(SUM(qty_change), 0) as total
            FROM stock_ledger
            WHERE event_type = 'INITIAL'
              AND store_code = ?
              AND event_date = ?
        """, (store_code, bootstrap_date.isoformat())).fetchone()["total"]

        return {
            "initial_events": initial_count,
            "total_units": initial_sum,
            "date": bootstrap_date.isoformat(),
            "store_code": store_code,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap stock_ledger from inventory Excel snapshot"
    )
    parser.add_argument(
        "xlsx_path",
        nargs="?",
        default="excel/Current_stock_2025-12-09.xlsx",
        help="Path to inventory Excel file (default: excel/Current_stock_2025-12-09.xlsx)",
    )
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date(2025, 12, 9),
        help="Date for INITIAL events (default: 2025-12-09)",
    )
    parser.add_argument(
        "--store",
        default="UNIVERSAL",
        help="Store code (default: UNIVERSAL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print each SKU processed",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Just verify existing bootstrap (no writes)",
    )

    args = parser.parse_args()

    # Resolve path
    xlsx_path = Path(args.xlsx_path)
    if not xlsx_path.is_absolute():
        xlsx_path = Path(__file__).parent.parent / args.xlsx_path

    if args.verify:
        result = verify_bootstrap(args.date, args.store)
        print(f"\nVerification for {result['date']} ({result['store_code']}):")
        print(f"  INITIAL events: {result['initial_events']}")
        print(f"  Total units:    {result['total_units']}")
        return

    if not xlsx_path.exists():
        print(f"ERROR: File not found: {xlsx_path}")
        sys.exit(1)

    result = bootstrap_ledger(
        xlsx_path=str(xlsx_path),
        bootstrap_date=args.date,
        store_code=args.store,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    if result["errors"]:
        sys.exit(1)

    print("\nBootstrap complete!")


if __name__ == "__main__":
    main()
