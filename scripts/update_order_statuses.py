#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED: Phase 12 Part 4: Update Order Statuses in CRM from Kaspi API.

===========================================================================
⚠️  DEPRECATION NOTICE ⚠️
===========================================================================
This script is DEPRECATED as of Phase 12 Part 7.

Status updates are now handled during the import process by:
    python scripts/import_orders_to_crm.py

The import script now:
1. Fetches 14 days of orders (including ARCHIVE state)
2. Updates existing orders' status columns (Статус, Принял, Выдал, Отменил)
3. Appends new orders

This script will be removed in a future version.
===========================================================================

Legacy functionality (deprecated):
- Reads existing OrderIDs from CRM (column H)
- Fetches current status from Kaspi API for each order
- Updates Status column (A) with: Завершен, Отменен, Возвращен, etc.
- Does NOT add new rows - only updates existing order statuses

Usage (DEPRECATED - use import_orders_to_crm.py instead):
    python scripts/update_order_statuses.py
    python scripts/update_order_statuses.py --dry-run
    python scripts/update_order_statuses.py --verbose
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import xlwings as xw
from dotenv import load_dotenv

# Emit deprecation warning when module is imported
warnings.warn(
    "update_order_statuses.py is DEPRECATED. "
    "Status updates now happen during import via import_orders_to_crm.py. "
    "This script will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2
)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    KaspiAuthError,
    STORE_TOKEN_MAP,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

# CRM paths
CRM_PATH = Path("~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx")
CRM_SHEET = "SALES_KSP_CRM_1"
CRM_TABLE = "tb_SalesRaw"

# Column positions (1-indexed)
STATUS_COL = 1      # Column A - Status (to update)
DATE_COL = 2        # Column B - Date
ORDER_ID_COL = 8    # Column H - OrderID

# API state → CRM Status mapping
# These are the values that will be written to Status column (A)
CRM_STATUS_MAP = {
    'NEW': 'Новый',
    'APPROVED_BY_BANK': 'Одобрен',
    'ACCEPTED_BY_MERCHANT': 'Принят',
    'ASSEMBLY': 'Собирается',
    'KASPI_DELIVERY': 'Ожидает КД',
    'DELIVERY': 'Доставляется',
    'PICKUP': 'Готов к выдаче',
    'COMPLETED': 'Завершен',
    'ARCHIVE': 'Завершен',  # Kaspi archives completed orders
    'CANCELLED': 'Отменен',
    'CANCELLING': 'Отменяется',
    'RETURNING': 'Возвращается',
    'RETURNED': 'Возвращен',
}


# =============================================================================
# CRM FUNCTIONS
# =============================================================================

def get_crm_orders(crm_path: Path, sheet_name: str, days_back: int = 7) -> Dict[str, int]:
    """
    Read existing OrderIDs from CRM and their row numbers using xlwings (fast).

    Uses batch read instead of cell-by-cell to avoid 30+ minute hangs on large CRMs.

    Args:
        crm_path: Path to CRM file
        sheet_name: Sheet name
        days_back: Only include orders from last N days

    Returns:
        Dict mapping OrderID -> row number (1-indexed)
    """
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(crm_path), read_only=True)
        sh = wb.sheets[sheet_name]

        # Find last row with data in column B (Date)
        last_row = sh.range("B1").end("down").row

        # Read all data at once (much faster than cell-by-cell)
        # Read columns B (date) and H (order_id) in one batch
        date_range = sh.range(f"B2:B{last_row}").value
        order_id_range = sh.range(f"H2:H{last_row}").value

        # Handle single-row case
        if not isinstance(date_range, list):
            date_range = [date_range]
            order_id_range = [order_id_range]

        wb.close()
    finally:
        app.quit()

    cutoff_date = datetime.now().date() - timedelta(days=days_back)
    order_map = {}

    for i, (date_val, order_id) in enumerate(zip(date_range, order_id_range)):
        row = i + 2  # Excel row (1-indexed, skip header)

        if date_val is None or order_id is None:
            continue

        # Parse date
        if isinstance(date_val, datetime):
            order_date = date_val.date()
        elif isinstance(date_val, str):
            try:
                if '.' in date_val:
                    parts = date_val.split('.')
                    order_date = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
                else:
                    order_date = datetime.strptime(date_val, "%Y-%m-%d").date()
            except (ValueError, IndexError):
                continue
        else:
            continue

        # Filter by date
        if order_date < cutoff_date:
            continue

        # Convert float to int to match API string format (741866233.0 -> "741866233")
        if isinstance(order_id, float):
            order_id = int(order_id)
        order_id_str = str(order_id).strip()
        if order_id_str:
            order_map[order_id_str] = row

    return order_map


def fetch_order_statuses(order_ids: Set[str], days_back: int = 7, verbose: bool = False) -> Dict[str, str]:
    """
    Fetch current status for orders from Kaspi API.

    Args:
        order_ids: Set of OrderIDs to fetch
        days_back: Lookback days for API query
        verbose: Print progress

    Returns:
        Dict mapping OrderID -> status string (for CRM)
    """
    statuses = {}
    since = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
        except KaspiAuthError as e:
            if verbose:
                print(f"  Skipping {store_code}: {e}")
            continue

        if verbose:
            print(f"  Fetching from {store_code}...")

        # Fetch ALL orders (no state filter) to get full status picture
        try:
            orders = client.list_all_orders(state=None, since=since)
        except Exception as e:
            if verbose:
                print(f"    Error: {e}")
            continue

        for order in orders:
            attrs = order.get('attributes', {})
            order_code = attrs.get('code', '')

            if order_code in order_ids:
                # Get state (API uses 'state' for lifecycle status)
                api_state = attrs.get('state', '')
                crm_status = CRM_STATUS_MAP.get(api_state, api_state)
                statuses[order_code] = crm_status

        if verbose:
            matched = sum(1 for oid in order_ids if oid in statuses)
            print(f"    Found {len(orders)} orders, matched {matched} from CRM")

    return statuses


def update_crm_statuses(
    crm_path: Path,
    sheet_name: str,
    order_rows: Dict[str, int],
    statuses: Dict[str, str],
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, int]:
    """
    Update Status column (A) in CRM for matched orders.

    Args:
        crm_path: Path to CRM file
        sheet_name: Sheet name
        order_rows: Dict mapping OrderID -> row number
        statuses: Dict mapping OrderID -> status string
        dry_run: If True, only show what would be updated
        verbose: Print progress

    Returns:
        Dict with stats: updated, skipped, not_found
    """
    stats = {"updated": 0, "skipped": 0, "not_found": 0}

    # Find orders to update
    updates = []
    for order_id, row in order_rows.items():
        if order_id in statuses:
            updates.append((row, statuses[order_id], order_id))
        else:
            stats["not_found"] += 1

    if not updates:
        print("  No status updates to make")
        return stats

    if dry_run:
        print(f"  [DRY-RUN] Would update {len(updates)} order statuses:")
        for row, status, oid in updates[:10]:  # Show first 10
            print(f"    Row {row}: Order {oid} -> {status}")
        if len(updates) > 10:
            print(f"    ... and {len(updates) - 10} more")
        stats["updated"] = len(updates)
        return stats

    # Use xlwings to update Status column
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(crm_path))
        sh = wb.sheets[sheet_name]

        for row, status, order_id in updates:
            current = sh.range((row, STATUS_COL)).value
            if current != status:
                sh.range((row, STATUS_COL)).value = status
                stats["updated"] += 1
                if verbose:
                    print(f"    Row {row}: {order_id} -> {status}")
            else:
                stats["skipped"] += 1

        wb.save()
        wb.close()
        print(f"  Updated {stats['updated']} statuses, skipped {stats['skipped']} (unchanged)")

    finally:
        app.quit()

    return stats


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Update order statuses in CRM from Kaspi API"
    )
    parser.add_argument(
        "--crm",
        type=Path,
        default=CRM_PATH,
        help="CRM file path"
    )
    parser.add_argument(
        "--sheet",
        default=CRM_SHEET,
        help="CRM sheet name"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback days (default: 7)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Load environment
    load_dotenv()

    print("=" * 60)
    print("  Order Status Update (Phase 12 Part 4)")
    print("=" * 60)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  CRM: {args.crm}")
    print(f"  Days: {args.days}")
    print()

    # Step 1: Read existing orders from CRM
    print("1. Reading orders from CRM...")
    order_rows = get_crm_orders(args.crm, args.sheet, args.days)
    print(f"   Found {len(order_rows)} orders in last {args.days} days")

    if not order_rows:
        print("   No orders to update")
        return

    # Step 2: Fetch statuses from API
    print("\n2. Fetching statuses from Kaspi API...")
    order_ids = set(order_rows.keys())
    statuses = fetch_order_statuses(order_ids, args.days, args.verbose)
    print(f"   Retrieved statuses for {len(statuses)} orders")

    # Step 3: Update CRM
    print("\n3. Updating CRM Status column...")
    stats = update_crm_statuses(
        args.crm, args.sheet, order_rows, statuses,
        dry_run=args.dry_run, verbose=args.verbose
    )

    # Summary
    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Orders in CRM (last {args.days} days): {len(order_rows)}")
    print(f"  Statuses fetched from API: {len(statuses)}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped (unchanged): {stats['skipped']}")
    print(f"  Not found in API: {stats['not_found']}")

    if args.dry_run:
        print("\n  [DRY-RUN] No changes were made")


if __name__ == "__main__":
    main()
