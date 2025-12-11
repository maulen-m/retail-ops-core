#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 11: Export Kaspi API Orders to ActiveOrders.xlsx

Downloads orders from Kaspi API and exports to Excel format matching
the manual Kaspi seller dashboard export.

Usage:
    python scripts/export_api_orders.py --all-stores
    python scripts/export_api_orders.py --store UNIVERSAL
    python scripts/export_api_orders.py --state KASPI_DELIVERY --days 7
    python scripts/export_api_orders.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    KaspiAuthError,
    KaspiNotFoundError,
    STORE_TOKEN_MAP,
)

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Excel column headers (must match Kaspi export exactly)
# NOTE: Some columns are MANUAL entry fields (not from API):
#   - Принял (Accepted by): warehouse staff fills when order is received
#   - Выдал (Issued by): warehouse staff fills when order is packed
#   - Отменил (Cancelled by): warehouse staff fills when order is cancelled
#   - Оформил (Processed by): warehouse staff fills who processed it
# These columns are intentionally empty on import.
EXCEL_COLUMNS = [
    '№ заказа',
    'Дата поступления заказа',
    'Название товара в Kaspi Магазине',  # From masterproduct.name (Kaspi public name)
    'Название в системе продавца',        # From offer.name (seller's internal name)
    'Артикул',
    'Сумма',
    'Категория',
    'Адрес самовывоза/доставки',
    'Дата изменения статуса',             # From API statusChangeDate (may be NULL for new orders)
    'Статус',
    'Причина отмены',
    'Способ оплаты',
    'Способ доставки',
    'Курьерская служба',
    'Принял',     # MANUAL: Accepted by (warehouse staff)
    'Выдал',      # MANUAL: Issued by (warehouse staff)
    'Отменил',    # MANUAL: Cancelled by (warehouse staff)
    'Оценка покупателя',
    'Отзыв покупателя',
    'Дата публикации отзыва',
    'Оформил',    # MANUAL: Processed by (warehouse staff)
    'Количество',
    'Стоимость доставки для покупателя',
    'Стоимость доставки для продавца',
    'Компенсация за доставку',
    'Требуется подписание',
    'Плановая дата передачи курьеру',
    'Телефон',
    'Склад передачи КД',
]

# API state → Russian status mapping
STATUS_MAP = {
    'NEW': 'Новый',
    'APPROVED_BY_BANK': 'Одобрен банком',
    'ACCEPTED_BY_MERCHANT': 'Принят продавцом',
    'ASSEMBLY': 'Собирается',
    'KASPI_DELIVERY': 'Ожидает передачи курьеру',
    'DELIVERY': 'Доставляется',
    'PICKUP': 'Готов к выдаче',
    'COMPLETED': 'Завершен',
    'CANCELLED': 'Отменен',
    'CANCELLING': 'Отменяется',
    'RETURNING': 'Возвращается',
    'RETURNED': 'Возвращен',
}

# Payment mode mapping
PAYMENT_MAP = {
    'PAY_WITH_CREDIT': 'Kaspi Рассрочка',
    'PREPAID': 'Kaspi Red / Kaspi Gold',
    'POSTPAID': 'При получении',
}

# Delivery mode mapping
DELIVERY_MAP = {
    'DELIVERY': 'Курьерская доставка',
    'PICKUP': 'Самовывоз',
    'DELIVERY_LOCAL': 'Доставка продавца',
    'DELIVERY_REGIONAL': 'Доставка в регион',
}

# Store code → Warehouse code mapping
STORE_WAREHOUSE_MAP = {
    'UNIVERSAL': '30000001_PP1',
    'ACMEWEAR': '30137883_PP1',
    '11KZ': '30290083_PP1',
    'STOREB': '30000002_PP1',
    'MELVIS': '30000002_PP1',  # Same as STOREB
}


# =============================================================================
# HELPERS
# =============================================================================

def timestamp_to_date(ts_ms: Optional[int]) -> Optional[str]:
    """Convert milliseconds timestamp to DD.MM.YYYY string."""
    if ts_ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000)
        return dt.strftime('%d.%m.%Y')
    except (ValueError, OSError):
        return None


def get_nested(d: dict, *keys, default=None) -> Any:
    """Safely get nested dict value."""
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
        if d is None:
            return default
    return d


# =============================================================================
# ORDER PROCESSING
# =============================================================================

# Cache for masterproduct names (reduces API calls)
_masterproduct_cache: Dict[str, str] = {}


def fetch_masterproduct_name(client: KaspiAPIClient, entry: dict) -> Optional[str]:
    """
    Fetch the Kaspi public product name from masterproduct.

    The masterproduct contains the official Kaspi product name that customers see.
    Results are cached to avoid repeated API calls.

    Args:
        client: KaspiAPIClient instance
        entry: Order entry dict containing product relationship

    Returns:
        Kaspi public product name or None if not available
    """
    global _masterproduct_cache

    # Get masterproduct ID from relationships
    relationships = entry.get('relationships', {})
    product_rel = relationships.get('product', {})
    product_data = product_rel.get('data', {})
    masterproduct_id = product_data.get('id')

    if not masterproduct_id:
        # Log first occurrence to help debug API structure issues
        if not hasattr(fetch_masterproduct_name, '_warned_no_id'):
            fetch_masterproduct_name._warned_no_id = True
            logger.warning(
                f"No masterproduct_id in entry relationships. "
                f"Available keys: {list(relationships.keys())}"
            )
        return None

    # Check cache first (only cache successful lookups)
    if masterproduct_id in _masterproduct_cache:
        cached = _masterproduct_cache[masterproduct_id]
        if cached:  # Only return if we have a real value
            return cached

    # Fetch from API
    try:
        response = client.get_masterproduct(masterproduct_id)
        if response.success and response.data:
            attrs = response.data.get('attributes', {})
            name = attrs.get('name', '')
            if name:
                _masterproduct_cache[masterproduct_id] = name
                return name
            else:
                logger.warning(f"Masterproduct {masterproduct_id} has no 'name' attribute")
        else:
            logger.warning(f"Masterproduct API returned no data for {masterproduct_id}")
    except Exception as e:
        # Log at WARNING level so it's visible (was DEBUG before)
        logger.warning(f"Failed to fetch masterproduct {masterproduct_id}: {e}")

    # DON'T cache failures - allow retry on next run
    return ''


def fetch_order_entries(client: KaspiAPIClient, order_code: str) -> List[dict]:
    """
    Fetch order entries (line items) for an order.

    Args:
        client: KaspiAPIClient instance
        order_code: Order code

    Returns:
        List of entry dicts
    """
    try:
        response = client.get_order_entries(order_code)
        if response.success:
            return response.data.get('data', [])
    except KaspiNotFoundError:
        logger.warning(f"Order {order_code} not found when fetching entries")
    except Exception as e:
        logger.warning(f"Failed to fetch entries for {order_code}: {e}")
    return []


def order_to_rows(
    order: dict,
    entries: List[dict],
    store_code: str,
    client: Optional[KaspiAPIClient] = None,
) -> List[Dict[str, Any]]:
    """
    Convert API order + entries to Excel rows.

    One row per entry (order line item).

    Args:
        order: Order dict from API
        entries: List of entry dicts
        store_code: Store code for warehouse mapping
        client: KaspiAPIClient for fetching masterproduct names (optional)

    Returns:
        List of row dicts matching EXCEL_COLUMNS
    """
    attrs = order.get('attributes', {})
    delivery = attrs.get('kaspiDelivery', {})
    customer = attrs.get('customer', {})

    # Extract and normalize customer phone (digits only)
    customer_phone = customer.get('cellPhone', '') or ''
    if customer_phone:
        customer_phone = ''.join(c for c in str(customer_phone) if c.isdigit())

    # Common fields for all entries
    order_code = attrs.get('code', '')
    creation_date = timestamp_to_date(attrs.get('creationDate'))
    status_change_date = timestamp_to_date(attrs.get('statusChangeDate'))

    # Status mapping - Kaspi export shows "Ожидает передачи курьеру" for KASPI_DELIVERY state
    # even when status is ACCEPTED_BY_MERCHANT
    api_state = attrs.get('state', '')
    api_status = attrs.get('status', '')

    # Use state for display if it's KASPI_DELIVERY (matches Kaspi export behavior)
    if api_state == 'KASPI_DELIVERY':
        russian_status = 'Ожидает передачи курьеру'
    else:
        russian_status = STATUS_MAP.get(api_status, STATUS_MAP.get(api_state, api_status))

    # Payment/delivery mapping
    payment_mode = PAYMENT_MAP.get(attrs.get('paymentMode', ''), attrs.get('paymentMode', ''))
    delivery_mode = DELIVERY_MAP.get(attrs.get('deliveryMode', ''), attrs.get('deliveryMode', ''))

    # Planned delivery date (API uses courierTransmissionPlanningDate)
    planned_date = timestamp_to_date(delivery.get('courierTransmissionPlanningDate'))

    # Warehouse
    warehouse = STORE_WAREHOUSE_MAP.get(store_code, '')

    # Signature required
    signature_required = 'Требуется' if attrs.get('signatureRequired') else 'Не требуется'

    # Address
    delivery_address = delivery.get('address', {})
    address_str = delivery_address.get('formattedAddress', '')

    # Courier service
    courier_service = delivery.get('courierService', '')

    # Cancellation reason
    cancel_reason = attrs.get('cancellationReason', '')

    rows = []

    if not entries:
        # Create single row with order-level data only
        row = {
            '№ заказа': order_code,
            'Дата поступления заказа': creation_date,
            'Название товара в Kaspi Магазине': '',
            'Название в системе продавца': '',
            'Артикул': '',
            'Сумма': attrs.get('totalPrice', 0),
            'Категория': '',
            'Адрес самовывоза/доставки': address_str,
            'Дата изменения статуса': status_change_date,
            'Статус': russian_status,
            'Причина отмены': cancel_reason,
            'Способ оплаты': payment_mode,
            'Способ доставки': delivery_mode,
            'Курьерская служба': courier_service,
            'Принял': '',
            'Выдал': '',
            'Отменил': '',
            'Оценка покупателя': '',
            'Отзыв покупателя': '',
            'Дата публикации отзыва': '',
            'Оформил': '',
            'Количество': 1,
            'Стоимость доставки для покупателя': delivery.get('customerDeliveryCost', 0),
            'Стоимость доставки для продавца': attrs.get('deliveryCost', 0),
            'Компенсация за доставку': delivery.get('deliveryCostCompensation', 0),
            'Требуется подписание': signature_required,
            'Плановая дата передачи курьеру': planned_date,
            'Телефон': customer_phone,
            'Склад передачи КД': warehouse,
        }
        rows.append(row)
    else:
        # Create one row per entry
        for entry in entries:
            entry_attrs = entry.get('attributes', {})
            offer = entry_attrs.get('offer', {})

            # Get Kaspi public name from masterproduct (if client provided)
            # offer.name is the merchant's internal name
            kaspi_public_name = ''
            if client:
                kaspi_public_name = fetch_masterproduct_name(client, entry) or ''

            # offer.name is the seller's internal product name
            seller_internal_name = offer.get('name', '')

            row = {
                '№ заказа': order_code,
                'Дата поступления заказа': creation_date,
                'Название товара в Kaspi Магазине': kaspi_public_name,  # From masterproduct (Kaspi official name)
                'Название в системе продавца': seller_internal_name,    # From offer (merchant's internal name)
                'Артикул': offer.get('code', ''),  # API uses 'code' for SKU
                'Сумма': entry_attrs.get('totalPrice', entry_attrs.get('price', 0)),
                'Категория': offer.get('category', ''),
                'Адрес самовывоза/доставки': address_str,
                'Дата изменения статуса': status_change_date,
                'Статус': russian_status,
                'Причина отмены': cancel_reason,
                'Способ оплаты': payment_mode,
                'Способ доставки': delivery_mode,
                'Курьерская служба': courier_service,
                'Принял': '',
                'Выдал': '',
                'Отменил': '',
                'Оценка покупателя': '',
                'Отзыв покупателя': '',
                'Дата публикации отзыва': '',
                'Оформил': '',
                'Количество': entry_attrs.get('quantity', 1),
                'Стоимость доставки для покупателя': delivery.get('customerDeliveryCost', 0),
                'Стоимость доставки для продавца': attrs.get('deliveryCost', 0),
                'Компенсация за доставку': delivery.get('deliveryCostCompensation', 0),
                'Требуется подписание': signature_required,
                'Плановая дата передачи курьеру': planned_date,
                'Телефон': customer_phone,
                'Склад передачи КД': warehouse,
            }
            rows.append(row)

    return rows


# =============================================================================
# EXPORT FUNCTIONS
# =============================================================================

def export_store_orders(
    store_code: str,
    state: Optional[str] = None,
    days: int = 7,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Export orders from a single store.

    Args:
        store_code: Store identifier
        state: Filter by state (e.g., KASPI_DELIVERY)
        days: Lookback days
        verbose: Print progress

    Returns:
        List of row dicts for Excel
    """
    try:
        client = KaspiAPIClient(store_code=store_code)
    except KaspiAuthError as e:
        logger.warning(f"Skipping {store_code}: {e}")
        return []

    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    if verbose:
        print(f"  Fetching orders from {store_code} (since {since})...")

    # Fetch orders
    orders = client.list_all_orders(state=state, since=since)

    if verbose:
        print(f"    Found {len(orders)} orders")

    all_rows = []

    for i, order in enumerate(orders):
        order_code = order.get('attributes', {}).get('code', '')

        # Fetch entries for this order
        entries = fetch_order_entries(client, order_code)

        # Convert to Excel rows (pass client for masterproduct name fetching)
        rows = order_to_rows(order, entries, store_code, client=client)
        all_rows.extend(rows)

        if verbose and (i + 1) % 10 == 0:
            print(f"    Processed {i + 1}/{len(orders)} orders...")

    if verbose:
        print(f"    Generated {len(all_rows)} rows")

    return all_rows


def export_all_stores(
    state: Optional[str] = None,
    days: int = 7,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Export orders from all configured stores.

    Args:
        state: Filter by state
        days: Lookback days
        verbose: Print progress

    Returns:
        List of all row dicts
    """
    all_rows = []

    for store_code in STORE_TOKEN_MAP.keys():
        rows = export_store_orders(
            store_code=store_code,
            state=state,
            days=days,
            verbose=verbose,
        )
        all_rows.extend(rows)

    return all_rows


def filter_rows_by_planned_date(
    rows: List[Dict[str, Any]],
    target_date: Optional[str] = None,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Filter rows by planned courier transmission date.

    Args:
        rows: List of row dicts
        target_date: Target date in DD.MM.YYYY format (default: today)
        verbose: Print filter stats

    Returns:
        Filtered list of rows
    """
    if not rows:
        return rows

    # Default to today
    if not target_date:
        target_date = datetime.now().strftime('%d.%m.%Y')

    filtered = []
    for row in rows:
        planned = row.get('Плановая дата передачи курьеру', '')
        if planned == target_date:
            filtered.append(row)

    if verbose:
        print(f"    Filtered: {len(filtered)}/{len(rows)} orders have planned date = {target_date}")

    return filtered


def write_excel(rows: List[Dict[str, Any]], output_path: Path) -> int:
    """
    Write rows to Excel file.

    Args:
        rows: List of row dicts
        output_path: Output file path

    Returns:
        Number of rows written
    """
    if not rows:
        return 0

    # Ensure column order matches EXCEL_COLUMNS
    df = pd.DataFrame(rows)

    # Reorder columns to match expected format
    ordered_cols = [c for c in EXCEL_COLUMNS if c in df.columns]
    df = df[ordered_cols]

    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to Excel
    df.to_excel(output_path, index=False, engine='openpyxl')

    return len(df)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Export Kaspi API orders to ActiveOrders.xlsx format"
    )
    parser.add_argument(
        '--store',
        type=str,
        choices=list(STORE_TOKEN_MAP.keys()),
        help='Export from single store'
    )
    parser.add_argument(
        '--all-stores',
        action='store_true',
        help='Export from all stores'
    )
    parser.add_argument(
        '--state',
        type=str,
        default='KASPI_DELIVERY',
        help='Filter by order state (default: KASPI_DELIVERY)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Lookback days (default: 7)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('excel_ui/ActiveOrders/ActiveOrders.xlsx'),
        help='Output Excel file path'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview only, do not write file'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--today-only',
        action='store_true',
        default=True,
        help='Only export orders with planned delivery date = today (default: True)'
    )
    parser.add_argument(
        '--all-dates',
        action='store_true',
        help='Export orders regardless of planned delivery date (overrides --today-only)'
    )
    parser.add_argument(
        '--planned-date',
        type=str,
        help='Filter by specific planned date (DD.MM.YYYY format)'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(levelname)s: %(message)s'
    )

    print("=" * 60)
    print("  Kaspi API → ActiveOrders.xlsx Export")
    print("=" * 60)

    if not args.store and not args.all_stores:
        print("Error: Specify --store STORE_CODE or --all-stores")
        sys.exit(1)

    state_filter = args.state if args.state.upper() != 'ALL' else None

    # Determine date filter for planned delivery date
    # Default: today only (unless --all-dates is specified)
    apply_date_filter = not args.all_dates
    target_date = args.planned_date  # Custom date or None (will default to today)

    print(f"  State filter: {state_filter or 'ALL'}")
    print(f"  Lookback: {args.days} days")
    if apply_date_filter:
        display_date = target_date or datetime.now().strftime('%d.%m.%Y')
        print(f"  Planned date filter: {display_date}")
    else:
        print(f"  Planned date filter: ALL dates")
    print(f"  Output: {args.output}")
    print()

    # Export orders
    if args.all_stores:
        print("Exporting from all stores...")
        rows = export_all_stores(
            state=state_filter,
            days=args.days,
            verbose=args.verbose,
        )
    else:
        print(f"Exporting from {args.store}...")
        rows = export_store_orders(
            store_code=args.store,
            state=state_filter,
            days=args.days,
            verbose=args.verbose,
        )

    print(f"\nTotal rows from API: {len(rows)}")

    # Print masterproduct fetch statistics
    if _masterproduct_cache:
        mp_success = sum(1 for v in _masterproduct_cache.values() if v)
        mp_failed = len(_masterproduct_cache) - mp_success
        print(f"  Masterproduct names: {mp_success} found, {mp_failed} missing")

    # Apply planned date filter (Phase 12 Part 3 - only pending orders for today)
    if apply_date_filter and rows:
        rows = filter_rows_by_planned_date(rows, target_date, verbose=args.verbose)
        print(f"Rows after date filter: {len(rows)}")

    if not rows:
        print("No orders found matching criteria.")
        return

    if args.dry_run:
        print("\n[DRY RUN] Would write but skipping.")
        # Show sample
        if rows:
            print("\nSample row:")
            sample = rows[0]
            for k in ['№ заказа', 'Статус', 'Название товара в Kaspi Магазине', 'Количество']:
                if k in sample:
                    print(f"  {k}: {sample[k]}")
        return

    # Write to Excel
    count = write_excel(rows, args.output)

    print(f"\n  Wrote {count} rows to {args.output}")
    print("  Done!")


if __name__ == "__main__":
    main()
