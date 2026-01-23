#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export On-Delivery Orders for Accounting

Downloads orders currently in transit (shipped but not yet received by customer)
from Kaspi API and exports to Excel. Also updates Balance_sheet_v3.xlsx.

Usage:
    python scripts/export_on_delivery_orders.py --verbose
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
EXCEL_COLUMNS = [
    '№ заказа',
    'Дата поступления заказа',
    'Название товара в Kaspi Магазине',
    'Название в системе продавца',
    'Артикул',
    'Сумма',
    'Категория',
    'Адрес самовывоза/доставки',
    'Дата изменения статуса',
    'Статус',
    'Причина отмены',
    'Способ оплаты',
    'Способ доставки',
    'Курьерская служба',
    'Принял',
    'Выдал',
    'Отменил',
    'Оценка покупателя',
    'Отзыв покупателя',
    'Дата публикации отзыва',
    'Оформил',
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
    'MELVIS': '30362323_PP1',
}

# Balance sheet configuration
BALANCE_SHEET_PATH = Path(
    '~/Documents/useful tables/Main crm spreadsheets/main tables/Balance_sheet_v3.xlsx'
)
BALANCE_SHEET_NAME = 'on_delivery_Orders'


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


def get_state_indicators(api_state: str) -> dict:
    """Map API state to Принял/Выдал/Отменил indicator columns."""
    accepted_states = {'ACCEPTED_BY_MERCHANT', 'ASSEMBLY', 'KASPI_DELIVERY',
                       'DELIVERY', 'PICKUP', 'COMPLETED', 'ARCHIVE'}
    issued_states = {'KASPI_DELIVERY', 'DELIVERY', 'PICKUP', 'COMPLETED', 'ARCHIVE'}
    cancelled_states = {'CANCELLED', 'CANCELLING', 'RETURNING', 'RETURNED'}

    return {
        'Принял': 'Да' if api_state in accepted_states else '',
        'Выдал': 'Да' if api_state in issued_states else '',
        'Отменил': 'Да' if api_state in cancelled_states else '',
    }


def format_european_number(value: Any) -> str:
    """
    Format number with European decimal separator (comma).
    Examples: 110.5 → '110,5', 12345 → '12345'
    """
    if value is None:
        return ''
    if isinstance(value, float):
        # Check if it's a whole number
        if value == int(value):
            return str(int(value))
        return str(value).replace('.', ',')
    return str(value)


# =============================================================================
# ON-DELIVERY FILTER
# =============================================================================

def is_on_delivery(order: dict) -> bool:
    """
    Check if order is truly on delivery (in transit to customer).

    Include orders that are:
    - assembled = true (already packaged)
    - courierTransmissionDate is set (courier has picked up)
    - signatureRequired = false (exclude signature required)

    Exclude:
    - "Упаковка" (Packaging): assembled=false
    - "Передача" (Handover pending): no courierTransmissionDate
    - "Требуется подписание"="Да": signatureRequired=true
    """
    attrs = order.get('attributes', {})
    delivery = attrs.get('kaspiDelivery', {})

    # Must be assembled
    if not attrs.get('assembled', False):
        return False

    # Must have been handed to courier
    if not delivery.get('courierTransmissionDate'):
        return False

    # Exclude signature required orders
    if attrs.get('signatureRequired', False):
        return False

    return True


# =============================================================================
# ORDER PROCESSING
# =============================================================================

# Cache for masterproduct names
_masterproduct_cache: Dict[str, str] = {}


def fetch_masterproduct_name(client: KaspiAPIClient, entry: dict) -> Optional[str]:
    """Fetch the Kaspi public product name from masterproduct."""
    global _masterproduct_cache

    relationships = entry.get('relationships', {})
    product_rel = relationships.get('product', {})
    product_data = product_rel.get('data', {})
    masterproduct_id = product_data.get('id')

    if not masterproduct_id:
        return None

    if masterproduct_id in _masterproduct_cache:
        cached = _masterproduct_cache[masterproduct_id]
        if cached:
            return cached

    try:
        response = client.get_masterproduct(masterproduct_id)
        if response.success and response.data:
            data_obj = response.data.get('data', {})
            attrs = data_obj.get('attributes', {})
            name = attrs.get('name', '')
            if name:
                _masterproduct_cache[masterproduct_id] = name
                return name
    except Exception as e:
        logger.warning(f"Failed to fetch masterproduct {masterproduct_id}: {e}")

    return ''


def fetch_order_entries(client: KaspiAPIClient, order_code: str) -> List[dict]:
    """Fetch order entries (line items) for an order."""
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
    """Convert API order + entries to Excel rows."""
    attrs = order.get('attributes', {})
    delivery = attrs.get('kaspiDelivery', {})
    customer = attrs.get('customer', {})

    # Extract and normalize customer phone
    customer_phone = customer.get('cellPhone', '') or ''
    if customer_phone:
        customer_phone = ''.join(c for c in str(customer_phone) if c.isdigit())

    # Common fields for all entries
    order_code = attrs.get('code', '')
    creation_date = timestamp_to_date(attrs.get('creationDate'))
    status_change_date = timestamp_to_date(attrs.get('statusChangeDate'))

    # Status mapping
    api_state = attrs.get('state', '')
    api_status = attrs.get('status', '')
    state_indicators = get_state_indicators(api_state)

    if api_state == 'KASPI_DELIVERY':
        russian_status = 'Ожидает передачи курьеру'
    else:
        russian_status = STATUS_MAP.get(api_status, STATUS_MAP.get(api_state, api_status))

    # Payment/delivery mapping
    payment_mode = PAYMENT_MAP.get(attrs.get('paymentMode', ''), attrs.get('paymentMode', ''))
    delivery_mode = DELIVERY_MAP.get(attrs.get('deliveryMode', ''), attrs.get('deliveryMode', ''))

    # Planned delivery date
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

    # Delivery costs:
    # - Buyer cost: prefer kaspiDelivery.customerDeliveryCost (if present), else attributes.deliveryCost
    # - Seller cost: attributes.deliveryCostForSeller (delivery commission)
    buyer_delivery_cost = delivery.get('customerDeliveryCost')
    if buyer_delivery_cost is None:
        buyer_delivery_cost = attrs.get('deliveryCost', 0)
    seller_delivery_cost = attrs.get('deliveryCostForSeller')
    if seller_delivery_cost is None:
        seller_delivery_cost = delivery.get('deliveryCostForSeller', 0)

    rows = []

    if not entries:
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
            'Принял': state_indicators['Принял'],
            'Выдал': state_indicators['Выдал'],
            'Отменил': state_indicators['Отменил'],
            'Оценка покупателя': '',
            'Отзыв покупателя': '',
            'Дата публикации отзыва': '',
            'Оформил': '',
            'Количество': 1,
            'Стоимость доставки для покупателя': buyer_delivery_cost or 0,
            'Стоимость доставки для продавца': seller_delivery_cost or 0,
            'Компенсация за доставку': delivery.get('deliveryCostCompensation', 0),
            'Требуется подписание': signature_required,
            'Плановая дата передачи курьеру': planned_date,
            'Телефон': customer_phone,
            'Склад передачи КД': warehouse,
        }
        rows.append(row)
    else:
        for entry in entries:
            entry_attrs = entry.get('attributes', {})
            offer = entry_attrs.get('offer', {})

            kaspi_public_name = ''
            if client:
                kaspi_public_name = fetch_masterproduct_name(client, entry) or ''

            seller_internal_name = offer.get('name', '')

            row = {
                '№ заказа': order_code,
                'Дата поступления заказа': creation_date,
                'Название товара в Kaspi Магазине': kaspi_public_name,
                'Название в системе продавца': seller_internal_name,
                'Артикул': offer.get('code', ''),
                'Сумма': entry_attrs.get('totalPrice', entry_attrs.get('price', 0)),
                'Категория': offer.get('category', ''),
                'Адрес самовывоза/доставки': address_str,
                'Дата изменения статуса': status_change_date,
                'Статус': russian_status,
                'Причина отмены': cancel_reason,
                'Способ оплаты': payment_mode,
                'Способ доставки': delivery_mode,
                'Курьерская служба': courier_service,
                'Принял': state_indicators['Принял'],
                'Выдал': state_indicators['Выдал'],
                'Отменил': state_indicators['Отменил'],
                'Оценка покупателя': '',
                'Отзыв покупателя': '',
                'Дата публикации отзыва': '',
                'Оформил': '',
                'Количество': entry_attrs.get('quantity', 1),
                'Стоимость доставки для покупателя': buyer_delivery_cost or 0,
                'Стоимость доставки для продавца': seller_delivery_cost or 0,
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

def export_on_delivery_orders(
    days: int = 14,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Export on-delivery orders from all configured stores.

    Args:
        days: Lookback days (default 14, max supported by API)
        verbose: Print progress

    Returns:
        List of row dicts for Excel
    """
    all_rows = []
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
        except KaspiAuthError as e:
            logger.warning(f"Skipping {store_code}: {e}")
            continue

        if verbose:
            print(f"  Fetching from {store_code} (since {since})...")

        # Fetch only KASPI_DELIVERY state (no archive - we want active deliveries)
        orders = client.list_all_orders(state='KASPI_DELIVERY', since=since)

        if verbose:
            print(f"    Found {len(orders)} orders in KASPI_DELIVERY state")

        # Filter to on-delivery orders immediately
        on_delivery_orders = [o for o in orders if is_on_delivery(o)]

        if verbose:
            print(f"    Filtered to {len(on_delivery_orders)} on-delivery orders")

        for i, order in enumerate(on_delivery_orders):
            order_code = order.get('attributes', {}).get('code', '')
            entries = fetch_order_entries(client, order_code)
            rows = order_to_rows(order, entries, store_code, client=client)
            all_rows.extend(rows)

            if verbose and (i + 1) % 10 == 0:
                print(f"    Processed {i + 1}/{len(on_delivery_orders)} orders...")

        if verbose:
            print(f"    Generated {len(all_rows)} total rows so far")

    return all_rows


def write_excel_with_european_format(
    rows: List[Dict[str, Any]],
    output_path: Path,
) -> int:
    """
    Write rows to Excel file with European number formatting.

    Args:
        rows: List of row dicts
        output_path: Output file path

    Returns:
        Number of rows written
    """
    if not rows:
        return 0

    # Columns that need European number formatting
    numeric_columns = [
        '№ заказа', 'Количество', 'Телефон',
        'Стоимость доставки для продавца',
        'Компенсация за доставку',
        'Стоимость доставки для покупателя',
        'Сумма',
    ]

    # Format numeric values with European decimal separator
    formatted_rows = []
    for row in rows:
        formatted_row = {}
        for col, val in row.items():
            if col in numeric_columns:
                formatted_row[col] = format_european_number(val)
            else:
                formatted_row[col] = val
        formatted_rows.append(formatted_row)

    df = pd.DataFrame(formatted_rows)

    # Reorder columns to match expected format
    ordered_cols = [c for c in EXCEL_COLUMNS if c in df.columns]
    df = df[ordered_cols]

    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to Excel
    df.to_excel(output_path, index=False, engine='openpyxl')

    return len(df)


def update_balance_sheet(rows: List[Dict[str, Any]], verbose: bool = False) -> bool:
    """
    Update Balance_sheet_v3.xlsx with on-delivery orders.

    Clears the on_delivery_Orders sheet (keeping headers) and appends new data.
    Uses xlwings to preserve formulas in other sheets.

    Args:
        rows: List of row dicts
        verbose: Print progress

    Returns:
        True if successful, False otherwise
    """
    if not BALANCE_SHEET_PATH.exists():
        if verbose:
            print(f"  Balance sheet not found: {BALANCE_SHEET_PATH}")
        return False

    try:
        import xlwings as xw
    except ImportError:
        if verbose:
            print("  xlwings not installed, skipping balance sheet update")
        return False

    try:
        if verbose:
            print(f"  Opening balance sheet: {BALANCE_SHEET_PATH}")

        # Open workbook (visible=False for background operation)
        app = xw.App(visible=False)
        wb = app.books.open(str(BALANCE_SHEET_PATH))

        try:
            # Get or create sheet
            if BALANCE_SHEET_NAME in [s.name for s in wb.sheets]:
                sheet = wb.sheets[BALANCE_SHEET_NAME]
            else:
                # Create new sheet if doesn't exist
                sheet = wb.sheets.add(BALANCE_SHEET_NAME)
                # Write headers
                sheet.range('A1').value = EXCEL_COLUMNS
                if verbose:
                    print(f"    Created new sheet: {BALANCE_SHEET_NAME}")

            # Clear data (keep row 1 headers)
            if sheet.range('A2').value is not None:
                # Find last row with data
                last_row = sheet.range('A1').end('down').row
                if last_row > 1:
                    sheet.range(f'A2:AC{last_row}').clear_contents()
                    if verbose:
                        print(f"    Cleared rows 2-{last_row}")

            # Columns that need European number formatting
            numeric_columns = [
                '№ заказа', 'Количество', 'Телефон',
                'Стоимость доставки для продавца',
                'Компенсация за доставку',
                'Стоимость доставки для покупателя',
                'Сумма',
            ]

            # Format and write new data
            if rows:
                data_rows = []
                for row in rows:
                    data_row = []
                    for col in EXCEL_COLUMNS:
                        val = row.get(col, '')
                        if col in numeric_columns:
                            val = format_european_number(val)
                        data_row.append(val)
                    data_rows.append(data_row)

                # Write all rows at once (faster)
                sheet.range('A2').value = data_rows
                if verbose:
                    print(f"    Wrote {len(data_rows)} rows to {BALANCE_SHEET_NAME}")

            wb.save()
            if verbose:
                print(f"    Saved balance sheet")

            return True

        finally:
            wb.close()
            app.quit()

    except Exception as e:
        logger.error(f"Failed to update balance sheet: {e}")
        if verbose:
            print(f"  ERROR updating balance sheet: {e}")
        return False


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Export on-delivery orders from Kaspi API"
    )
    parser.add_argument(
        '--days',
        type=int,
        default=14,
        help='Lookback days (default: 14, max supported by Kaspi API)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview only, do not write files'
    )
    parser.add_argument(
        '--skip-balance-sheet',
        action='store_true',
        help='Skip updating Balance_sheet_v3.xlsx'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv(PROJECT_ROOT / '.env')

    # Setup logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(levelname)s: %(message)s'
    )

    # Create timestamped output path
    now = datetime.now()
    folder_name = now.strftime('%d%m%Y_%H%M')  # ddmmyyyy_hhmm
    file_name = now.strftime('on_delivery_orders_%d_%m_%Y_%H%M.xlsx')

    output_folder = PROJECT_ROOT / 'excel_ui' / 'ActiveOrders' / 'on_delivery' / folder_name
    output_path = output_folder / file_name

    print("=" * 60)
    print("  Export On-Delivery Orders")
    print("  (shipped, awaiting customer receipt)")
    print("=" * 60)
    print()
    print(f"  Lookback: {args.days} days")
    print(f"  Output: {output_path}")
    print()

    # Export orders
    print("Fetching on-delivery orders from all stores...")
    rows = export_on_delivery_orders(days=args.days, verbose=args.verbose)

    print(f"\nTotal on-delivery rows: {len(rows)}")

    if not rows:
        print("\nNo on-delivery orders found.")
        return

    if args.dry_run:
        print("\n[DRY RUN] Would write but skipping.")
        if rows:
            print("\nSample row:")
            sample = rows[0]
            for k in ['№ заказа', 'Статус', 'Название в системе продавца', 'Количество']:
                if k in sample:
                    print(f"  {k}: {sample[k]}")
        return

    # Write to timestamped Excel file
    print(f"\nWriting to {output_path}...")
    count = write_excel_with_european_format(rows, output_path)
    print(f"  Wrote {count} rows")

    # Update balance sheet
    if not args.skip_balance_sheet:
        print(f"\nUpdating balance sheet...")
        success = update_balance_sheet(rows, verbose=args.verbose)
        if success:
            print(f"  Updated {BALANCE_SHEET_NAME} sheet in Balance_sheet_v3.xlsx")
        else:
            print(f"  Failed to update balance sheet (check if file is open)")

    print("\nDone!")


if __name__ == "__main__":
    main()
