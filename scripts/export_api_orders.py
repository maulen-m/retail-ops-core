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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
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
from core.integrations.kaspi_order_stage import (
    StageCode,
    classify_kaspi_order_stage,
    kaspi_order_to_russian_status,
    stage_to_crm_indicators,
)
from core.stores.roster import load_sync_enabled_kaspi_store_codes
from core.utils.kaspi_dates import planned_date_from_order

logger = logging.getLogger(__name__)


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError("Expected boolean: true/false")

# =============================================================================
# CONFIGURATION
# =============================================================================

# Kaspi API dates are in Asia/Almaty timezone
ALMATY_TZ = ZoneInfo("Asia/Almaty")

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


PENDING_EXPORT_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
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


# =============================================================================
# HELPERS
# =============================================================================

def timestamp_to_date(ts_ms: Optional[int]) -> Optional[str]:
    """Convert milliseconds timestamp to DD.MM.YYYY string (Asia/Almaty)."""
    if ts_ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=ALMATY_TZ)
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


def _extract_delivery_costs(order: dict) -> tuple[Optional[float], Optional[float]]:
    """Extract buyer/seller delivery costs if present (None if missing)."""
    attrs = order.get('attributes', {}) if isinstance(order, dict) else {}
    delivery = attrs.get('kaspiDelivery', {}) if isinstance(attrs.get('kaspiDelivery', {}), dict) else {}

    buyer_cost = delivery.get('customerDeliveryCost')
    if buyer_cost is None:
        buyer_cost = attrs.get('deliveryCost')

    seller_cost = attrs.get('deliveryCostForSeller')
    if seller_cost is None:
        seller_cost = delivery.get('deliveryCostForSeller')

    return buyer_cost, seller_cost


def _order_missing_delivery_costs(order: dict) -> bool:
    """Return True when delivery fields required for export are missing."""
    buyer_cost, seller_cost = _extract_delivery_costs(order)
    return buyer_cost is None or seller_cost is None or seller_cost == 0


def _maybe_refetch_order_details(
    client: KaspiAPIClient,
    order: dict,
    verbose: bool = False,
    force: bool = False,
) -> dict:
    """
    Refetch full order details by ID when delivery cost fields may be stale.

    Some list responses return deliveryCostForSeller=0 even when the detail
    endpoint has a non-zero value, so allow forcing a refresh.
    """
    if not force and not _order_missing_delivery_costs(order):
        return order

    order_id = order.get('id')
    order_code = order.get('attributes', {}).get('code', '')

    resp = None
    if order_id:
        resp = client.get_order_by_id(order_id)
    elif order_code:
        resp = client.get_order(order_code)

    if not resp or not resp.success or not resp.data:
        if verbose:
            logger.warning(f"Refetch failed for order {order_code or order_id}")
        return order

    data = resp.data
    # JSON:API response might be {"data": {...}}
    if isinstance(data, dict) and isinstance(data.get('data'), dict):
        return data['data']
    if isinstance(data, dict) and data.get('type') == 'orders':
        return data

    return order


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
            # JSON:API response structure: {"data": {"attributes": {"name": ...}}}
            # response.data contains the full JSON, need to access nested 'data' first
            data_obj = response.data.get('data', {})
            attrs = data_obj.get('attributes', {})
            name = attrs.get('name', '')
            if name:
                _masterproduct_cache[masterproduct_id] = name
                return name
            else:
                logger.warning(f"Masterproduct {masterproduct_id} has no 'name' attribute in: {list(attrs.keys())}")
        else:
            logger.warning(f"Masterproduct API returned no data for {masterproduct_id}")
    except Exception as e:
        # Log at WARNING level so it's visible (was DEBUG before)
        logger.warning(f"Failed to fetch masterproduct {masterproduct_id}: {e}")

    # DON'T cache failures - allow retry on next run
    return ''


def fetch_order_entries(
    client: KaspiAPIClient,
    order_code: str,
    *,
    order_id: Optional[str] = None,
) -> List[dict]:
    """
    Fetch order entries (line items) for an order.

    Args:
        client: KaspiAPIClient instance
        order_code: Order code
        order_id: Optional Base64 order ID from list response

    Returns:
        List of entry dicts
    """
    try:
        # Fast path: when list response already includes Base64 order ID, skip
        # the extra get-order lookup used by get_order_entries(order_code).
        if order_id and hasattr(client, "get_order_entries_by_id"):
            response = client.get_order_entries_by_id(order_id)
        else:
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

    api_state = attrs.get('state', '')
    stage = classify_kaspi_order_stage(order)
    state_indicators = stage_to_crm_indicators(stage)
    russian_status = kaspi_order_to_russian_status(order)

    # Payment/delivery mapping
    payment_mode = PAYMENT_MAP.get(attrs.get('paymentMode', ''), attrs.get('paymentMode', ''))
    delivery_mode = DELIVERY_MAP.get(attrs.get('deliveryMode', ''), attrs.get('deliveryMode', ''))

    # Planned handover date: keep consistent with DB sync/reporting logic
    # (creation-time cutoff based) to avoid API/DB/CRM date mismatches.
    planned_date_obj = planned_date_from_order(order, store_code=store_code)
    if planned_date_obj:
        planned_date = planned_date_obj.strftime("%d.%m.%Y")
    else:
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

    # Delivery costs
    buyer_delivery_cost, seller_delivery_cost = _extract_delivery_costs(order)
    if buyer_delivery_cost is None:
        buyer_delivery_cost = 0
    if seller_delivery_cost is None:
        seller_delivery_cost = 0

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

def export_store_orders(
    store_code: str,
    state: Optional[str] = None,
    days: int = 14,
    verbose: bool = False,
    include_archive: bool = True,
    refetch_missing_costs: bool = False,
    db_direct: bool = False,
    db_direct_dry_run: bool = False,
    delivery_type: Optional[str] = None,
    signature_required: Optional[bool] = None,
    include_orders: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Export orders from a single store.

    Args:
        store_code: Store identifier
        state: Filter by state (e.g., KASPI_DELIVERY)
        days: Lookback days (default 14, max supported by API)
        verbose: Print progress
        include_archive: Also fetch ARCHIVE orders (completed/cancelled/returned)

    Returns:
        List of row dicts for Excel
    """
    try:
        client = KaspiAPIClient(store_code=store_code)
    except KaspiAuthError as e:
        logger.warning(f"Skipping {store_code}: {e}")
        return []

    since = (datetime.now(ALMATY_TZ) - timedelta(days=days)).strftime('%Y-%m-%d')

    if verbose:
        print(f"  Fetching orders from {store_code} (since {since})...")

    # Fetch active orders
    orders = client.list_all_orders(
        state=state,
        since=since,
        delivery_type=delivery_type,
        signature_required=signature_required,
        include_orders=include_orders,
    )

    if verbose:
        print(f"    Found {len(orders)} active orders")

    if state == 'KASPI_DELIVERY':
        pending_orders = []
        for order in orders:
            if classify_kaspi_order_stage(order) in PENDING_EXPORT_STAGES:
                pending_orders.append(order)
        if verbose and len(pending_orders) != len(orders):
            print(
                f"    Pending-stage filter: kept {len(pending_orders)}/{len(orders)} "
                "orders (excluded already shipped / terminal delivery-stage orders)"
            )
        orders = pending_orders

    # Also fetch ARCHIVE orders if requested (completed, cancelled, returned)
    if include_archive and state != 'ARCHIVE':
        if verbose:
            print(f"    Fetching ARCHIVE orders...")
        archive_orders = client.list_all_orders(
            state='ARCHIVE',
            since=since,
            delivery_type=delivery_type,
            signature_required=signature_required,
            include_orders=include_orders,
        )
        if verbose:
            print(f"    Found {len(archive_orders)} archive orders")

        # Deduplicate by order code (in case of overlap)
        seen_codes = {o.get('attributes', {}).get('code') for o in orders}
        for order in archive_orders:
            code = order.get('attributes', {}).get('code')
            if code and code not in seen_codes:
                orders.append(order)
                seen_codes.add(code)

    if verbose:
        print(f"    Total: {len(orders)} orders (after dedup)")

    all_rows = []

    for i, order in enumerate(orders):
        if refetch_missing_costs and _order_missing_delivery_costs(order):
            order = _maybe_refetch_order_details(
                client,
                order,
                verbose=verbose,
                force=False,
            )

        order_code = order.get('attributes', {}).get('code', '')
        order_id = order.get('id')

        # Fetch entries for this order
        entries = fetch_order_entries(client, order_code, order_id=order_id)

        # Convert to Excel rows (pass client for masterproduct name fetching)
        rows = order_to_rows(order, entries, store_code, client=client)
        all_rows.extend(rows)

        if verbose and (i + 1) % 10 == 0:
            print(f"    Processed {i + 1}/{len(orders)} orders...")

    if verbose:
        print(f"    Generated {len(all_rows)} rows")

    if db_direct:
        try:
            stats = ingest_rows_to_db(
                all_rows,
                store_code=store_code,
                dry_run=db_direct_dry_run,
            )
            if verbose:
                logger.info(
                    f"{store_code}: DB direct ingest "
                    f"inserted={stats.get('inserted', 0)} "
                    f"updated={stats.get('updated', 0)} "
                    f"errors={stats.get('errors', 0)}"
                )
        except Exception as e:
            logger.warning(f"{store_code}: DB direct ingest failed: {e}")

    return all_rows


def export_all_stores(
    state: Optional[str] = None,
    days: int = 14,
    verbose: bool = False,
    include_archive: bool = True,
    refetch_missing_costs: bool = False,
    db_direct: bool = False,
    db_direct_dry_run: bool = False,
    delivery_type: Optional[str] = None,
    signature_required: Optional[bool] = None,
    include_orders: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Export orders from all configured stores.

    Args:
        state: Filter by state
        days: Lookback days (default 14)
        verbose: Print progress
        include_archive: Also fetch ARCHIVE orders

    Returns:
        List of all row dicts
    """
    all_rows = []

    for store_code in (store for store in load_sync_enabled_kaspi_store_codes() if store in STORE_TOKEN_MAP):
        rows = export_store_orders(
            store_code=store_code,
            state=state,
            days=days,
            verbose=verbose,
            include_archive=include_archive,
            refetch_missing_costs=refetch_missing_costs,
            db_direct=db_direct,
            db_direct_dry_run=db_direct_dry_run,
            delivery_type=delivery_type,
            signature_required=signature_required,
            include_orders=include_orders,
        )
        all_rows.extend(rows)

    return all_rows


def ingest_rows_to_db(
    rows: List[Dict[str, Any]],
    store_code: str,
    dry_run: bool = False,
) -> dict:
    """
    Ingest ActiveOrders-format rows directly into fact_orders_kaspi.

    Args:
        rows: ActiveOrders-style rows (Russian column headers)
        store_code: Store code (UNIVERSAL, ACMEWEAR, etc.)
        dry_run: If True, do not write to DB

    Returns:
        Stats dict from ingest_records
    """
    if not rows:
        return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    # Lazy imports to avoid circular deps
    from core.db import get_db
    from core.parsers.kaspi_export_parser import parse_active_orders_df, load_column_config
    from scripts.ingest_kaspi_export import ingest_orders

    df = pd.DataFrame(rows)
    source_file = f"API_DIRECT_{store_code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    parsed = parse_active_orders_df(df, source_file=source_file, config=load_column_config())

    if dry_run:
        return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    with get_db() as conn:
        stats = ingest_orders(parsed.orders, conn)

    return stats


def _parse_planned_date(value: Any) -> Optional[date]:
    """Parse planned date from known formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value_str = str(value).strip()
    if not value_str:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value_str, fmt).date()
        except ValueError:
            continue
    return None


def filter_rows_by_planned_date(
    rows: List[Dict[str, Any]],
    target_date: Optional[str] = None,
    verbose: bool = False,
    include_overdue: bool = False,
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
        target_date = datetime.now(ALMATY_TZ).strftime('%d.%m.%Y')
    target_dt = _parse_planned_date(target_date) if include_overdue else None

    filtered = []
    for row in rows:
        planned = row.get('Плановая дата передачи курьеру', '')
        if include_overdue:
            planned_dt = _parse_planned_date(planned)
            if planned_dt and target_dt and planned_dt <= target_dt:
                filtered.append(row)
        else:
            if planned == target_date:
                filtered.append(row)

    if verbose:
        if include_overdue:
            print(
                f"    Filtered: {len(filtered)}/{len(rows)} orders have planned date <= {target_date}"
            )
        else:
            print(
                f"    Filtered: {len(filtered)}/{len(rows)} orders have planned date = {target_date}"
            )

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
        '--delivery-type',
        type=str,
        choices=['DELIVERY', 'PICKUP'],
        help='Filter by delivery type (use only when state != PICKUP)'
    )
    parser.add_argument(
        '--signature-required',
        type=_parse_bool,
        help='Filter by signatureRequired (true/false)'
    )
    parser.add_argument(
        '--include-orders',
        type=str,
        default='user',
        help='Include extra order data (comma-separated). Use \"none\" to disable.'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=14,
        help='Lookback days (default: 14, max supported by Kaspi API)'
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
        '--include-overdue',
        action='store_true',
        help='Include orders with planned delivery date <= target date (today by default)'
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
    parser.add_argument(
        '--no-archive',
        action='store_true',
        help='Skip fetching ARCHIVE orders (completed/cancelled/returned)'
    )
    parser.add_argument(
        '--refetch-missing-costs',
        action='store_true',
        help='Refetch full order details to get accurate delivery costs'
    )
    parser.add_argument(
        '--db-direct',
        action='store_true',
        help='Ingest API rows directly into DB (fact_orders_kaspi)'
    )
    parser.add_argument(
        '--db-direct-dry-run',
        action='store_true',
        help='Dry run for --db-direct (no DB writes)'
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
    if args.all_dates and args.include_overdue:
        logger.warning("Both --all-dates and --include-overdue set; using --all-dates.")
        args.include_overdue = False
    if args.all_dates:
        date_mode = "all"
    elif args.include_overdue:
        date_mode = "overdue"
    else:
        date_mode = "exact"
    apply_date_filter = date_mode != "all"
    target_date = args.planned_date  # Custom date or None (will default to today)

    include_archive = not args.no_archive
    include_orders = None
    if args.include_orders:
        if args.include_orders.strip().lower() != 'none':
            include_orders = [s.strip() for s in args.include_orders.split(',') if s.strip()]

    print(f"  State filter: {state_filter or 'ALL'}")
    print(f"  Lookback: {args.days} days")
    print(f"  Include archive: {include_archive}")
    print(f"  Refetch missing costs: {args.refetch_missing_costs}")
    print(f"  DB direct ingest: {args.db_direct}")
    if apply_date_filter:
        display_date = target_date or datetime.now(ALMATY_TZ).strftime('%d.%m.%Y')
        if date_mode == "overdue":
            print(f"  Planned date filter: <= {display_date}")
        else:
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
            include_archive=include_archive,
            refetch_missing_costs=args.refetch_missing_costs,
            db_direct=args.db_direct,
            db_direct_dry_run=args.db_direct_dry_run,
            delivery_type=args.delivery_type,
            signature_required=args.signature_required,
            include_orders=include_orders,
        )
    else:
        print(f"Exporting from {args.store}...")
        rows = export_store_orders(
            store_code=args.store,
            state=state_filter,
            days=args.days,
            verbose=args.verbose,
            include_archive=include_archive,
            refetch_missing_costs=args.refetch_missing_costs,
            db_direct=args.db_direct,
            db_direct_dry_run=args.db_direct_dry_run,
            delivery_type=args.delivery_type,
            signature_required=args.signature_required,
            include_orders=include_orders,
        )

    print(f"\nTotal rows from API: {len(rows)}")

    # Print masterproduct fetch statistics
    if _masterproduct_cache:
        mp_success = sum(1 for v in _masterproduct_cache.values() if v)
        mp_failed = len(_masterproduct_cache) - mp_success
        print(f"  Masterproduct names: {mp_success} found, {mp_failed} missing")

    # Apply planned date filter (Phase 12 Part 3 - only pending orders for today)
    if apply_date_filter and rows:
        rows = filter_rows_by_planned_date(
            rows,
            target_date,
            verbose=args.verbose,
            include_overdue=(date_mode == "overdue"),
        )
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
