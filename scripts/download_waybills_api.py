#!/usr/bin/env python3
"""
Download Kaspi waybills via API for today's pending orders (with lookback).

Phase 12: Automated waybill download - aligned with CRM order selection.

IMPORTANT: Only downloads waybills for orders that:
1. Exist in CRM with MY_SIZE filled
2. Have planned_date within the target lookback window (default 14 days)
3. Are in KASPI_DELIVERY state (shipped via API)

This ensures we download only pending waybills, not all historical ones.

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
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import DEFAULT_DB_PATH, get_db
from core.integrations.kaspi_api_client import (
    DOWNLOAD_TIMEOUT,
    KaspiAPIClient,
    KaspiAuthError,
    STORE_TOKEN_MAP,
)
from core.paths import data_path, get_data_root

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kaspi dates are in Asia/Almaty timezone
ALMATY_TZ = ZoneInfo("Asia/Almaty")
# Default paths
DEFAULT_OUTPUT_DIR = data_path("excel_ui", "ActiveOrders", "waybills")
DEFAULT_CRM_PATH = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
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

# DB/CRM store values -> API store code
DB_STORE_TO_API = {
    # API store codes (pass-through)
    'UNIVERSAL': 'UNIVERSAL',
    'ACMEWEAR': 'ACMEWEAR',
    '11KZ': '11KZ',
    'MELVIS': 'MELVIS',
    'STOREB': 'STOREB',
    'STORE-B': 'STOREB',
    # CRM/Excel codes
    '30137883_PP1': 'ACMEWEAR',
    '30000001_PP1': 'UNIVERSAL',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STOREB',
    # Internal store codes
    'PP1': 'ACMEWEAR',
    'PP2': 'ACMEWEAR',
}


def resolve_db_path(explicit: Optional[Path]) -> Optional[Path]:
    """Resolve DB path, preferring DATA_DIR if present."""
    if explicit:
        return explicit
    data_db = data_path("db", "app.db")
    if data_db.exists():
        return data_db
    if DEFAULT_DB_PATH.exists():
        return DEFAULT_DB_PATH
    return None


def normalize_api_store_code(value: Any) -> Optional[str]:
    """Normalize a store identifier to an API store code."""
    if pd.isna(value) or value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    upper = raw.upper()

    if upper in STORE_TOKEN_MAP:
        return upper

    for display, api_code in STORE_NAME_TO_API_CODE.items():
        if display.lower() == raw.lower():
            return api_code

    api_code = DB_STORE_TO_API.get(upper)
    if api_code:
        return api_code

    # Fallback: check store mapping entries
    for code, name in STORE_MAP.items():
        if code.lower() == raw.lower() or name.lower() == raw.lower():
            return STORE_NAME_TO_API_CODE.get(name, api_code)

    return None


def _timestamp_to_date(ts: Optional[int]) -> Optional[date]:
    """Convert millisecond timestamp to date."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000, tz=ALMATY_TZ).date()
    except (ValueError, OSError):
        return None


def _planned_date_from_order(order: dict) -> Optional[date]:
    """Extract planned courier transmission date from API order."""
    delivery = order.get('attributes', {}).get('kaspiDelivery', {})
    planned_ts = delivery.get('courierTransmissionPlanningDate') or delivery.get('plannedDeliveryDate')
    return _timestamp_to_date(planned_ts)


def get_target_orders_from_api(
    store_code: str,
    target_date: date,
    since_days: int,
    exact_date: bool = True,
    all_dates: bool = False,
    verbose: bool = False,
) -> list[dict]:
    """Fetch KASPI_DELIVERY orders from API and filter by planned date."""
    client = KaspiAPIClient(store_code=store_code)
    since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')

    orders = client.list_all_orders(state='KASPI_DELIVERY', since=since)
    if verbose:
        print(f"    API returned {len(orders)} orders for {store_code}")

    filtered = []
    for order in orders:
        planned_date = _planned_date_from_order(order)
        if planned_date is None:
            continue
        if all_dates:
            if planned_date <= target_date:
                filtered.append(order)
        elif exact_date:
            if planned_date == target_date:
                filtered.append(order)
        else:
            # Default to exact-date selection
            if planned_date == target_date:
                filtered.append(order)

    if verbose:
        print(f"    Filtered to {len(filtered)} orders for {target_date}")
    return filtered

    api_code = DB_STORE_TO_API.get(upper)
    if api_code:
        return api_code

    compact = upper.replace(" ", "").replace("-", "")
    for key, candidate in DB_STORE_TO_API.items():
        if key.replace(" ", "").replace("-", "") == compact:
            return candidate

    return None


def _is_pdf_bytes(data: bytes) -> bool:
    """Quick check that the payload looks like a PDF."""
    if not data:
        return False
    return data.lstrip().startswith(b"%PDF")


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


def get_target_order_ids_from_db(
    db_path: Path,
    target_date: date,
    store_filter: Optional[str] = None,
    exact_date: bool = True,
    lookback_days: Optional[int] = None,
) -> dict[str, set[str]]:
    """
    Get order IDs from the database (fact_orders_kaspi) ready for waybill download.

    Filters for orders where:
    - assigned_size OR my_size is present
    - planned_shipment_date == target_date (if exact_date=True) OR <= target_date

    Returns dict: api_store_code -> set of order_ids
    """
    if not db_path or not db_path.exists():
        logger.warning(f"DB not found: {db_path}")
        return {}

    store_filter_api = normalize_api_store_code(store_filter) if store_filter else None

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            logger.warning("DB missing fact_orders_kaspi table; falling back to CRM")
            return {}

        query = """
            SELECT order_id, store_code, assigned_size, my_size, planned_shipment_date
            FROM fact_orders_kaspi
            WHERE (
                (assigned_size IS NOT NULL AND assigned_size != '')
                OR (my_size IS NOT NULL AND my_size != '')
            )
        """
        params = []
        if exact_date:
            query += " AND planned_shipment_date = ?"
            params.append(target_date.isoformat())
        else:
            query += " AND planned_shipment_date <= ?"
            params.append(target_date.isoformat())
            if lookback_days is not None:
                min_date = (target_date - timedelta(days=lookback_days)).isoformat()
                query += " AND planned_shipment_date >= ?"
                params.append(min_date)

        rows = conn.execute(query, params).fetchall()

    orders_by_store: dict[str, set[str]] = defaultdict(set)
    skipped_no_store = 0

    for row in rows:
        order_id = str(row["order_id"]).strip()
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id:
            continue

        api_store = normalize_api_store_code(row["store_code"])
        if not api_store:
            skipped_no_store += 1
            continue

        if store_filter_api and api_store != store_filter_api:
            continue

        orders_by_store[api_store].add(order_id)

    total_orders = sum(len(ids) for ids in orders_by_store.values())
    if exact_date:
        logger.info(f"Found {total_orders} orders in DB (date exact {target_date})")
    else:
        if lookback_days is not None:
            min_date = target_date - timedelta(days=lookback_days)
            logger.info(
                f"Found {total_orders} orders in DB (date range {min_date} to {target_date})"
            )
        else:
            logger.info(
                f"Found {total_orders} orders in DB (date <= {target_date})"
            )
    if skipped_no_store:
        logger.info(f"Skipped {skipped_no_store} DB rows with unknown store codes")

    return dict(orders_by_store)


def get_target_order_ids_from_crm(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    store_filter: Optional[str] = None,
    exact_date: bool = True,
    lookback_days: Optional[int] = None,
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
    skipped_unknown_store = 0
    store_filter_api = normalize_api_store_code(store_filter) if store_filter else None

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

        # Date filter: exact match or <= target with optional lookback
        if exact_date:
            if planned_date != target_date:
                skipped_wrong_date += 1
                continue
        else:
            if planned_date and planned_date > target_date:
                skipped_wrong_date += 1
                continue
            if lookback_days is not None and planned_date:
                min_date = target_date - timedelta(days=lookback_days)
                if planned_date < min_date:
                    skipped_wrong_date += 1
                    continue

        # Get store name
        store_name = row.get('STORE_NAME')
        if pd.isna(store_name):
            store_name = row.get('Склад передачи КД')
        store_name = normalize_store_name(store_name)
        api_store = normalize_api_store_code(store_name)
        if not api_store:
            skipped_unknown_store += 1
            continue

        # Filter by store if specified
        if store_filter_api and api_store != store_filter_api:
            continue

        orders_by_store[api_store].add(order_id)

    total_orders = sum(len(ids) for ids in orders_by_store.values())
    if exact_date:
        logger.info(f"Found {total_orders} orders in CRM (date exact {target_date})")
    else:
        if lookback_days is not None:
            min_date = target_date - timedelta(days=lookback_days)
            logger.info(
                f"Found {total_orders} orders in CRM (date range {min_date} to {target_date})"
            )
        else:
            logger.info(f"Found {total_orders} orders in CRM (date <= {target_date})")
    logger.info(f"Skipped {skipped_no_size} without MY_SIZE, {skipped_wrong_date} wrong date")
    if skipped_unknown_store:
        logger.info(f"Skipped {skipped_unknown_store} with unknown stores")

    return dict(orders_by_store)


def download_waybills_for_store(
    store_code: str,
    target_order_ids: set[str],
    output_dir: Path,
    since_days: int = 7,  # Phase 12 Part 6: reduced from 14 to avoid API limits
    download_timeout: int = DOWNLOAD_TIMEOUT,
    dry_run: bool = False,
    verbose: bool = False,
    prefetched_orders: Optional[list[dict]] = None,
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
    invalid_pdf = 0
    errors = []

    if not target_order_ids:
        return {
            'downloaded': 0,
            'skipped_not_target': 0,
            'missing_waybill': 0,
            'already_exists': 0,
            'invalid_pdf': 0,
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
            'invalid_pdf': 0,
            'errors': [f"Auth error: {e}"],
        }

    if prefetched_orders is not None:
        orders = prefetched_orders
        if verbose:
            print(f"    Using {len(orders)} pre-filtered API orders for {store_code}")
    else:
        # Fetch orders in KASPI_DELIVERY state
        since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')

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
            result = client.download_waybill(waybill_url, timeout=download_timeout)
            if result.success:
                if not _is_pdf_bytes(result.data):
                    invalid_pdf += 1
                    errors.append(f"{order_code}: Invalid PDF payload")
                    consecutive_errors += 1
                    if verbose:
                        print(f"      {order_code}: Invalid PDF payload")
                else:
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
        'invalid_pdf': invalid_pdf,
        'errors': errors,
    }


def download_all_waybills(
    output_dir: Path,
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    db_path: Optional[Path] = None,
    store_filter: Optional[str] = None,
    since_days: int = 7,  # Phase 12 Part 6: reduced from 14 to avoid API limits
    download_timeout: int = DOWNLOAD_TIMEOUT,
    dry_run: bool = False,
    verbose: bool = False,
    all_dates: bool = False,
    exact_date: bool = False,
    fallback_crm: bool = False,
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
    all_dates: If True, include all orders with planned_date <= target_date (no lookback floor).
    exact_date: If True, include only orders with planned_date == target_date.

    Returns:
        Combined summary dict
    """
    # Ensure output directory exists
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
    elif verbose:
        print(f"  [DRY RUN] Would create directory: {output_dir}")

    # Get target order IDs from DB first, fallback to CRM
    # Primary selection: Kaspi API planned date (freshest)
    target_orders_by_store: dict[str, set[str]] = {}
    orders_by_store: dict[str, list[dict]] = {}
    source_label = None

    stores = list(STORE_TOKEN_MAP.keys())
    if store_filter:
        store_filter_api = normalize_api_store_code(store_filter)
        if store_filter_api:
            stores = [store_filter_api]

    for store_code in stores:
        try:
            orders = get_target_orders_from_api(
                store_code,
                target_date,
                since_days=since_days,
                exact_date=exact_date or not all_dates,
                all_dates=all_dates,
                verbose=verbose,
            )
        except Exception as exc:
            logger.warning(f"{store_code}: API selection failed: {exc}")
            continue

        if orders:
            orders_by_store[store_code] = orders
            target_orders_by_store[store_code] = {
                o.get('attributes', {}).get('code', '')
                for o in orders
                if o.get('attributes', {}).get('code', '')
            }

    if target_orders_by_store:
        source_label = "Kaspi API (planned date)"

    # Optional fallback to DB/CRM if API returned nothing
    if not target_orders_by_store and fallback_crm:
        resolved_db_path = resolve_db_path(db_path)
        if resolved_db_path:
            target_orders_by_store = get_target_order_ids_from_db(
                resolved_db_path,
                target_date,
                store_filter,
                exact_date=exact_date,
                lookback_days=None if all_dates or exact_date else since_days,
            )
            if target_orders_by_store:
                source_label = f"DB ({resolved_db_path})"

        if not target_orders_by_store and crm_path:
            target_orders_by_store = get_target_order_ids_from_crm(
                crm_path,
                sheet_name,
                target_date,
                store_filter,
                exact_date=exact_date,
                lookback_days=None if all_dates or exact_date else since_days,
            )
            if target_orders_by_store:
                source_label = f"CRM ({crm_path})"

    if not target_orders_by_store:
        print("  No orders found for the target date.")
        return {
            'downloaded': 0,
            'skipped_not_target': 0,
            'missing_waybill': 0,
            'already_exists': 0,
            'invalid_pdf': 0,
            'errors': [],
        }
    if source_label:
        print(f"  Using {source_label} for order selection")

    total_downloaded = 0
    total_skipped_not_target = 0
    total_missing_waybill = 0
    total_already_exists = 0
    total_invalid_pdf = 0
    all_errors = []

    # Process each store
    for api_store_code, order_ids in target_orders_by_store.items():
        if api_store_code not in STORE_TOKEN_MAP:
            logger.warning(f"Unknown store: {api_store_code}, skipping {len(order_ids)} orders")
            continue

        print(f"\n  Processing {api_store_code} ({len(order_ids)} target orders)...")

        result = download_waybills_for_store(
            store_code=api_store_code,
            target_order_ids=order_ids,
            output_dir=output_dir,
            since_days=since_days,
            download_timeout=download_timeout,
            dry_run=dry_run,
            verbose=verbose,
            prefetched_orders=orders_by_store.get(api_store_code),
        )

        total_downloaded += result['downloaded']
        total_skipped_not_target += result['skipped_not_target']
        total_missing_waybill += result['missing_waybill']
        total_already_exists += result['already_exists']
        total_invalid_pdf += result['invalid_pdf']
        all_errors.extend(result['errors'])

        # Per-store summary
        print(f"    Downloaded: {result['downloaded']}, "
              f"Exists: {result['already_exists']}, "
              f"No waybill: {result['missing_waybill']}, "
              f"Invalid PDF: {result['invalid_pdf']}")

    return {
        'downloaded': total_downloaded,
        'skipped_not_target': total_skipped_not_target,
        'missing_waybill': total_missing_waybill,
        'already_exists': total_already_exists,
        'invalid_pdf': total_invalid_pdf,
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
        '--db-path',
        type=Path,
        default=None,
        help='Optional DB path (defaults to DATA_DIR/db/app.db if present)'
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
        '--download-timeout',
        type=int,
        default=DOWNLOAD_TIMEOUT,
        help=f'Waybill download timeout in seconds (default: {DOWNLOAD_TIMEOUT})'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview only, do not download'
    )
    parser.add_argument(
        '--all-dates',
        action='store_true',
        help='Include all orders with planned_date <= today (no lookback floor)'
    )
    parser.add_argument(
        '--exact-date',
        action='store_true',
        help='Only include orders with planned_date == target_date'
    )
    parser.add_argument(
        '--fallback-crm',
        action='store_true',
        help='Fallback to DB/CRM selection if API returns no orders'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    if args.all_dates and args.exact_date:
        logger.warning("Both --all-dates and --exact-date set; using --all-dates.")
        args.exact_date = False

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(ALMATY_TZ).date()

    print("=" * 60)
    print("  Kaspi Waybill Download (CRM-Aligned)")
    print("=" * 60)
    print(f"  Data root: {get_data_root()}")
    print(f"  Output: {args.output}")
    print(f"  CRM: {args.crm_file}")
    resolved_db_path = resolve_db_path(args.db_path)
    print(f"  DB: {resolved_db_path or 'None'}")
    print(f"  Target date: {target_date}")
    if args.all_dates:
        date_mode_str = "all dates <= target"
    elif args.exact_date:
        date_mode_str = "exact date only (today's batch)"
    else:
        date_mode_str = "exact date only (today's batch)"
    print(f"  Date mode: {date_mode_str}")
    print(f"  API since: {args.days} days")
    print(f"  Download timeout: {args.download_timeout}s")
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
        db_path=resolved_db_path,
        store_filter=args.store,
        since_days=args.days,
        download_timeout=args.download_timeout,
        dry_run=args.dry_run,
        verbose=args.verbose,
        all_dates=args.all_dates,
        exact_date=args.exact_date,
        fallback_crm=args.fallback_crm,
    )

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Downloaded: {result['downloaded']}")
    print(f"  Already existed: {result['already_exists']}")
    print(f"  Missing waybill URL: {result['missing_waybill']}")
    print(f"  Invalid PDF payloads: {result['invalid_pdf']}")
    print(f"  Skipped (not in target set): {result['skipped_not_target']}")
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
