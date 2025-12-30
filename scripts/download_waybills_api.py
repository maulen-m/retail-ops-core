#!/usr/bin/env python3
"""
Download Kaspi waybills via API for TODAY's pending orders only.

Phase 12: Automated waybill download - aligned with CRM order selection.

IMPORTANT: Only downloads waybills for orders that:
1. Exist in CRM with MY_SIZE filled
2. Have planned_date <= today
3. Are in KASPI_DELIVERY state (shipped via API)

This ensures we download ~55 pending waybills, NOT 207+ historical ones.

Usage:
    python scripts/download_waybills_api.py --verbose
    python scripts/download_waybills_api.py --dry-run
    python scripts/download_waybills_api.py --store UNIVERSAL
"""

import argparse
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    KaspiAuthError,
    STORE_TOKEN_MAP,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default paths
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "waybills"
DEFAULT_CRM_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET_NAME = "SALES_KSP_CRM_1"

# Store code mapping
STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
}

# Reverse mapping: display name -> API store code
STORE_NAME_TO_API_CODE = {
    'AcmeWear': 'ACMEWEAR',
    'Universal': 'UNIVERSAL',
    '11KZ': '11KZ',
    'STORE-B': 'STOREB',
}


def parse_date(value: Any) -> Optional[date]:
    """Parse date from various formats."""
    if pd.isna(value) or value is None:
        return None

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    value_str = str(value).strip()

    # DD.MM.YYYY format
    try:
        return datetime.strptime(value_str, "%d.%m.%Y").date()
    except ValueError:
        pass

    # YYYY-MM-DD format
    try:
        return datetime.strptime(value_str, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Try pandas
    try:
        return pd.to_datetime(value, dayfirst=True).date()
    except (ValueError, TypeError):
        pass

    return None


def normalize_store_name(value: Any) -> str:
    """Normalize store name from various formats."""
    if pd.isna(value) or not value:
        return "UNKNOWN"

    store_str = str(value).strip()

    # Direct match
    if store_str in STORE_MAP:
        return STORE_MAP[store_str]

    # Already a display name
    if store_str in STORE_NAME_TO_API_CODE:
        return store_str

    # Case-insensitive lookup
    for code, name in STORE_MAP.items():
        if code.lower() == store_str.lower() or name.lower() == store_str.lower():
            return name

    return store_str


def get_target_order_ids_from_crm(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    store_filter: Optional[str] = None,
    exact_date: bool = True,
) -> dict[str, set[str]]:
    """
    Get order IDs from CRM that are ready for waybill download.

    Filters for orders where:
    - MY_SIZE is filled (indicates order is processed)
    - planned_date == target_date (if exact_date=True) OR planned_date <= target_date

    The exact_date=True mode ensures we only download waybills for TODAY's
    shipping batch (~55 orders), not all historical orders (200+).

    Returns dict: store_name -> set of order_ids
    """
    if not crm_path.exists():
        logger.warning(f"CRM file not found: {crm_path}")
        return {}

    logger.info(f"Reading CRM from {crm_path}")
    df = pd.read_excel(crm_path, sheet_name=sheet_name)

    orders_by_store: dict[str, set[str]] = defaultdict(set)
    skipped_no_size = 0
    skipped_wrong_date = 0

    for _, row in df.iterrows():
        # Check MY_SIZE is filled
        my_size = str(row.get('MY_SIZE', '')).strip()
        if not my_size or my_size.lower() in ('nan', 'none', ''):
            skipped_no_size += 1
            continue

        # Get order_id
        order_id = row.get('OrderID')
        if pd.isna(order_id):
            order_id = row.get('№ заказа')
        if pd.isna(order_id):
            continue

        order_id = str(order_id).strip()
        if order_id.endswith('.0'):
            order_id = order_id[:-2]

        # Get planned date
        planned_date = parse_date(row.get('PLANNED_SHIPPING_DATE'))
        if not planned_date:
            planned_date = parse_date(row.get('Плановая дата передачи курьеру'))

        # Date filter: exact match (today's batch only) or <= target
        if exact_date:
            # Only orders scheduled for TODAY (not past orders)
            if planned_date != target_date:
                skipped_wrong_date += 1
                continue
        else:
            # Include all orders up to target date
            if planned_date and planned_date > target_date:
                skipped_wrong_date += 1
                continue

        # Get store name
        store_name = row.get('STORE_NAME')
        if pd.isna(store_name):
            store_name = row.get('Склад передачи КД')
        store_name = normalize_store_name(store_name)

        # Filter by store if specified
        if store_filter and store_name != store_filter:
            continue

        orders_by_store[store_name].add(order_id)

    total_orders = sum(len(ids) for ids in orders_by_store.values())
    date_mode = "exact" if exact_date else "<="
    logger.info(f"Found {total_orders} orders in CRM (date {date_mode} {target_date})")
    logger.info(f"Skipped {skipped_no_size} without MY_SIZE, {skipped_wrong_date} wrong date")

    return dict(orders_by_store)


def download_waybills_for_store(
    store_code: str,
    target_order_ids: set[str],
    output_dir: Path,
    since_days: int = 7,  # Phase 12 Part 6: reduced from 14 to avoid API limits
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Download waybills for specific orders in a store.

    Only downloads waybills for orders in target_order_ids set.

    Args:
        store_code: Store identifier for API
        target_order_ids: Set of order IDs we want waybills for
        output_dir: Output directory for PDFs
        since_days: Lookback days for API query
        dry_run: Preview only
        verbose: Print progress

    Returns:
        Summary dict with counts
    """
    downloaded = 0
    skipped_not_target = 0
    missing_waybill = 0
    already_exists = 0
    errors = []

    if not target_order_ids:
        return {
            'downloaded': 0,
            'skipped_not_target': 0,
            'missing_waybill': 0,
            'already_exists': 0,
            'errors': [],
        }

    # Initialize client
    try:
        client = KaspiAPIClient(store_code=store_code)
    except KaspiAuthError as e:
        return {
            'downloaded': 0,
            'skipped_not_target': 0,
            'missing_waybill': 0,
            'already_exists': 0,
            'errors': [f"Auth error: {e}"],
        }

    # Fetch orders in KASPI_DELIVERY state
    since = (datetime.now() - timedelta(days=since_days)).strftime('%Y-%m-%d')

    if verbose:
        print(f"    Fetching KASPI_DELIVERY orders from {store_code}...")

    orders = client.list_all_orders(state='KASPI_DELIVERY', since=since)

    if verbose:
        print(f"    API returned {len(orders)} orders, filtering to {len(target_order_ids)} targets")

    # Phase 12 Part 6: Circuit breaker - skip remaining orders after 3 consecutive errors
    MAX_CONSECUTIVE_ERRORS = 3
    consecutive_errors = 0

    for order in orders:
        order_code = order.get('attributes', {}).get('code', '')
        if not order_code:
            continue

        # CRITICAL: Only process orders in our target set from CRM
        if order_code not in target_order_ids:
            skipped_not_target += 1
            continue

        # Check if already downloaded
        output_path = output_dir / f"{order_code}.pdf"
        if output_path.exists():
            already_exists += 1
            if verbose:
                print(f"      {order_code}: Already exists, skipping")
            continue

        # Get waybill URL
        waybill_url = client.get_waybill_url(order)
        if not waybill_url:
            missing_waybill += 1
            if verbose:
                print(f"      {order_code}: No waybill URL yet")
            continue

        if dry_run:
            downloaded += 1
            if verbose:
                print(f"      {order_code}: Would download")
            continue

        # Download waybill
        try:
            result = client.download_waybill(waybill_url)
            if result.success:
                # Save PDF
                output_path.write_bytes(result.data)
                downloaded += 1
                consecutive_errors = 0  # Reset on success
                if verbose:
                    print(f"      {order_code}: Downloaded OK")
            else:
                errors.append(f"{order_code}: {result.error}")
                consecutive_errors += 1
                if verbose:
                    print(f"      {order_code}: Download failed - {result.error}")
        except Exception as e:
            errors.append(f"{order_code}: {str(e)}")
            consecutive_errors += 1
            if verbose:
                print(f"      {order_code}: Exception - {e}")

        # Circuit breaker: stop processing this store after too many consecutive failures
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            logger.warning(f"Circuit breaker: {consecutive_errors} consecutive errors for {store_code}, skipping remaining orders")
            if verbose:
                print(f"      ⚠️ Stopping {store_code}: too many consecutive failures")
            break

    return {
        'downloaded': downloaded,
        'skipped_not_target': skipped_not_target,
        'missing_waybill': missing_waybill,
        'already_exists': already_exists,
        'errors': errors,
    }


def download_all_waybills(
    output_dir: Path,
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    store_filter: Optional[str] = None,
    since_days: int = 7,  # Phase 12 Part 6: reduced from 14 to avoid API limits
    dry_run: bool = False,
    verbose: bool = False,
    all_dates: bool = False,
) -> dict:
    """
    Download waybills for pending orders from CRM.

    Args:
        output_dir: Output directory for PDFs
        crm_path: Path to CRM Excel file
        sheet_name: CRM sheet name
        target_date: Target date for filtering
        store_filter: Optional single store filter
        since_days: Lookback days for API
        dry_run: Preview only
        verbose: Print progress
        all_dates: If True, include all orders with planned_date <= target_date.
                   If False (default), only include orders with planned_date == target_date.

    Returns:
        Combined summary dict
    """
    # Ensure output directory exists
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    elif verbose:
        print(f"  [DRY RUN] Would create directory: {output_dir}")

    # Get target order IDs from CRM
    # exact_date=True means only today's batch; exact_date=False means all historical
    target_orders_by_store = get_target_order_ids_from_crm(
        crm_path, sheet_name, target_date, store_filter, exact_date=not all_dates
    )

    if not target_orders_by_store:
        print("  No orders found in CRM with MY_SIZE filled.")
        return {
            'downloaded': 0,
            'skipped_not_target': 0,
            'missing_waybill': 0,
            'already_exists': 0,
            'errors': [],
        }

    total_downloaded = 0
    total_skipped_not_target = 0
    total_missing_waybill = 0
    total_already_exists = 0
    all_errors = []

    # Process each store
    for store_name, order_ids in target_orders_by_store.items():
        # Get API store code
        api_store_code = STORE_NAME_TO_API_CODE.get(store_name)
        if not api_store_code:
            logger.warning(f"Unknown store: {store_name}, skipping {len(order_ids)} orders")
            continue

        print(f"\n  Processing {store_name} ({len(order_ids)} target orders)...")

        result = download_waybills_for_store(
            store_code=api_store_code,
            target_order_ids=order_ids,
            output_dir=output_dir,
            since_days=since_days,
            dry_run=dry_run,
            verbose=verbose,
        )

        total_downloaded += result['downloaded']
        total_skipped_not_target += result['skipped_not_target']
        total_missing_waybill += result['missing_waybill']
        total_already_exists += result['already_exists']
        all_errors.extend(result['errors'])

        # Per-store summary
        print(f"    Downloaded: {result['downloaded']}, "
              f"Exists: {result['already_exists']}, "
              f"No waybill: {result['missing_waybill']}")

    return {
        'downloaded': total_downloaded,
        'skipped_not_target': total_skipped_not_target,
        'missing_waybill': total_missing_waybill,
        'already_exists': total_already_exists,
        'errors': all_errors,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Download Kaspi waybills via API (CRM-aligned)"
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help='Output directory for waybill PDFs'
    )
    parser.add_argument(
        '--crm-file',
        type=Path,
        default=DEFAULT_CRM_PATH,
        help='CRM Excel file path'
    )
    parser.add_argument(
        '--sheet',
        default=DEFAULT_SHEET_NAME,
        help='CRM sheet name'
    )
    parser.add_argument(
        '--store',
        choices=['AcmeWear', 'Universal', '11KZ', 'STORE-B'],
        help='Filter by store (optional)'
    )
    parser.add_argument(
        '--date',
        help='Target date (default: today, format: YYYY-MM-DD)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=14,
        help='Lookback days for API query (default: 14)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview only, do not download'
    )
    parser.add_argument(
        '--all-dates',
        action='store_true',
        help='Include all orders with planned_date <= today (not just today\'s batch)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = date.today()

    print("=" * 60)
    print("  Kaspi Waybill Download (CRM-Aligned)")
    print("=" * 60)
    print(f"  Output: {args.output}")
    print(f"  CRM: {args.crm_file}")
    print(f"  Target date: {target_date}")
    date_mode_str = "all dates <= target" if args.all_dates else "exact date only (today's batch)"
    print(f"  Date mode: {date_mode_str}")
    print(f"  Lookback: {args.days} days")
    if args.store:
        print(f"  Store filter: {args.store}")
    if args.dry_run:
        print("  [DRY RUN MODE - No downloads]")

    # Download waybills
    result = download_all_waybills(
        output_dir=args.output,
        crm_path=args.crm_file,
        sheet_name=args.sheet,
        target_date=target_date,
        store_filter=args.store,
        since_days=args.days,
        dry_run=args.dry_run,
        verbose=args.verbose,
        all_dates=args.all_dates,
    )

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Downloaded: {result['downloaded']}")
    print(f"  Already existed: {result['already_exists']}")
    print(f"  Missing waybill URL: {result['missing_waybill']}")
    print(f"  Skipped (not in CRM target): {result['skipped_not_target']}")
    if result['errors']:
        print(f"  Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"    - {err}")
        if len(result['errors']) > 5:
            print(f"    ... and {len(result['errors']) - 5} more")

    if args.dry_run:
        print(f"\n  [DRY RUN] Would download {result['downloaded']} waybills.")
    else:
        print(f"\n  Waybills saved to: {args.output}")


if __name__ == "__main__":
    main()
