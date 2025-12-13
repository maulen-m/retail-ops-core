#!/usr/bin/env python3
"""
Phase 12 Part 6 Task 7: Optimized waybill download.

Downloads waybills directly from Kaspi API filtered by planned date,
WITHOUT reading CRM first. This saves 30-60 seconds of xlwings overhead.

Usage:
    python scripts/download_waybills_v2.py [--date YYYY-MM-DD] [--verbose] [--dry-run]
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables before importing API client
load_dotenv(PROJECT_ROOT / '.env')

from core.integrations.kaspi_api_client import KaspiAPIClient, STORE_TOKEN_MAP

logger = logging.getLogger(__name__)

# Output directory for waybills
WAYBILL_DIR = Path(__file__).parent.parent / "excel_ui" / "ActiveOrders" / "waybills"

# Circuit breaker settings
MAX_CONSECUTIVE_ERRORS = 5


def timestamp_to_date(ts: Optional[int]) -> Optional[date]:
    """Convert millisecond timestamp to date."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000).date()
    except (ValueError, OSError):
        return None


def get_todays_orders_from_api(
    store_code: str,
    target_date: date,
    since_days: int = 7,
    verbose: bool = False,
) -> List[dict]:
    """
    Get orders from Kaspi API filtered by planned delivery date.

    Args:
        store_code: Store code (UNIVERSAL, ACMEWEAR, etc.)
        target_date: Target date to filter orders
        since_days: How many days back to query API
        verbose: Print progress

    Returns:
        List of orders with planned_date == target_date
    """
    client = KaspiAPIClient(store_code)
    since = (datetime.now() - timedelta(days=since_days)).strftime('%Y-%m-%d')

    # Fetch all KASPI_DELIVERY orders
    orders = client.list_all_orders(state='KASPI_DELIVERY', since=since)

    if verbose:
        print(f"    API returned {len(orders)} KASPI_DELIVERY orders")

    # Filter by planned date
    todays_orders = []
    for order in orders:
        delivery = order.get('attributes', {}).get('kaspiDelivery', {})
        planned_ts = delivery.get('courierTransmissionPlanningDate')
        planned = timestamp_to_date(planned_ts)

        if planned == target_date:
            todays_orders.append(order)

    if verbose:
        print(f"    Filtered to {len(todays_orders)} orders for {target_date}")

    return todays_orders


def download_waybills_for_store(
    store_code: str,
    orders: List[dict],
    output_dir: Path,
    verbose: bool = False,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Download waybills for a list of orders.

    Returns:
        Dict with counts: downloaded, skipped_exists, skipped_no_url, errors
    """
    client = KaspiAPIClient(store_code)
    stats = {'downloaded': 0, 'skipped_exists': 0, 'skipped_no_url': 0, 'errors': 0}
    consecutive_errors = 0

    output_dir.mkdir(parents=True, exist_ok=True)

    for order in orders:
        order_code = order.get('attributes', {}).get('code', '')
        if not order_code:
            continue

        # Check if already downloaded
        pdf_path = output_dir / f"{order_code}.pdf"
        if pdf_path.exists():
            stats['skipped_exists'] += 1
            continue

        # Get waybill URL
        delivery = order.get('attributes', {}).get('kaspiDelivery', {})
        waybill_url = delivery.get('waybill')

        if not waybill_url:
            stats['skipped_no_url'] += 1
            continue

        if dry_run:
            if verbose:
                print(f"      [DRY-RUN] Would download: {order_code}")
            stats['downloaded'] += 1
            continue

        # Download waybill
        try:
            response = client.download_waybill(waybill_url)
            if response.success and response.data:
                pdf_path.write_bytes(response.data)
                stats['downloaded'] += 1
                consecutive_errors = 0
                if verbose:
                    print(f"      Downloaded: {order_code}")
            else:
                error_msg = response.error if hasattr(response, 'error') else 'Unknown error'
                if verbose:
                    print(f"      Error {order_code}: {error_msg}")
                stats['errors'] += 1
                consecutive_errors += 1
        except Exception as e:
            stats['errors'] += 1
            consecutive_errors += 1
            if verbose:
                print(f"      Error {order_code}: {e}")

        # Circuit breaker
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            if verbose:
                print(f"      Circuit breaker: {consecutive_errors} consecutive errors, stopping {store_code}")
            break

    return stats


def main():
    parser = argparse.ArgumentParser(description='Download waybills from Kaspi API (V2 - no CRM read)')
    parser.add_argument('--date', help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--store', help='Single store to process (default: all)')
    parser.add_argument('--since-days', type=int, default=7, help='Days to look back in API')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    args = parser.parse_args()

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        target_date = date.today()

    print(f"\n{'='*60}")
    print(f"  Waybill Download V2 (API-direct, no CRM read)")
    print(f"  Target date: {target_date}")
    print(f"{'='*60}\n")

    # Determine stores to process
    if args.store:
        stores = [args.store.upper()]
    else:
        stores = list(STORE_TOKEN_MAP.keys())

    total_stats = {'downloaded': 0, 'skipped_exists': 0, 'skipped_no_url': 0, 'errors': 0}

    for store_code in stores:
        if store_code not in STORE_TOKEN_MAP:
            print(f"  Unknown store: {store_code}")
            continue

        print(f"\n  {store_code}")

        # Get today's orders from API
        try:
            orders = get_todays_orders_from_api(
                store_code, target_date, args.since_days, args.verbose
            )
        except Exception as e:
            print(f"    API error: {e}")
            continue

        if not orders:
            print(f"    No orders for {target_date}")
            continue

        # Download waybills
        stats = download_waybills_for_store(
            store_code, orders, WAYBILL_DIR, args.verbose, args.dry_run
        )

        for key in total_stats:
            total_stats[key] += stats[key]

        print(f"    Downloaded: {stats['downloaded']}, Exists: {stats['skipped_exists']}, "
              f"No URL: {stats['skipped_no_url']}, Errors: {stats['errors']}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Summary")
    print(f"{'='*60}")
    print(f"  Downloaded: {total_stats['downloaded']}")
    print(f"  Already existed: {total_stats['skipped_exists']}")
    print(f"  No waybill URL: {total_stats['skipped_no_url']}")
    print(f"  Errors: {total_stats['errors']}")
    print(f"  Output: {WAYBILL_DIR}")


if __name__ == '__main__':
    main()
