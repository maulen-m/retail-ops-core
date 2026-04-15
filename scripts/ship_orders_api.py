#!/usr/bin/env python3
"""
Ship Kaspi orders via API - Set package count and move to "Передача курьеру".

Phase 12: Automated Kaspi shipping workflow.

For orders in CRM with MY_SIZE filled and planned_date <= today:
1. Calculate package count using heavy item logic
2. Call assemble_order(order_code, parcel_count) to set "Количество мест"
3. This moves orders from "Упаковка" to "Передача курьеру"

Usage:
    python scripts/ship_orders_api.py --verbose
    python scripts/ship_orders_api.py --dry-run
    python scripts/ship_orders_api.py --store UNIVERSAL
    python scripts/ship_orders_api.py --today-only
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
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
from core.ops.crm_operational_view import select_operational_crm_rows
from core.paths import data_path, get_data_root
from core.utils.kaspi_dates import parse_kaspi_date
from core.integrations.kaspi_api_client import (
    APIResponse,
    KaspiAPIClient,
    KaspiAuthError,
    KaspiNotFoundError,
    KaspiWriteDisabledError,
    STORE_TOKEN_MAP,
)
from core.waybill.pdf_grouper import _extract_name_core as extract_name_core
from core.ops.shipment_health import classify_ship_health

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kaspi dates are in Asia/Almaty timezone
ALMATY_TZ = ZoneInfo("Asia/Almaty")

# Default paths
DEFAULT_CRM_PATH = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET_NAME = "SALES_KSP_CRM_1"

# Store code mapping
STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
    '30362323_PP1': 'Store-C',
}

# Reverse mapping: display name -> store code for API
STORE_NAME_TO_API_CODE = {
    'AcmeWear': 'ACMEWEAR',
    'Universal': 'UNIVERSAL',
    '11KZ': '11KZ',
    'STORE-B': 'STOREB',
    'Store-C': 'MELVIS',
}
API_CODE_TO_STORE_NAME = {v: k for k, v in STORE_NAME_TO_API_CODE.items()}

# Heavy items (always separate package)
HEAVY_ITEMS = {
    'Костюм_мужской_Хус',
    'Line51',
    'Принт_5в1_черный',
    'Костюм_Ромбик_ДЕТСКИЙ',
    'Спортивный_3в1_детский_черный',
    'CL_NEW-CLO2_MEN_SUIT-61_BLACK',
    'CL_NEW-CLO2_MEN_SUIT-51_BLACK_GREY',
    'CL_NK_MEN_LINE51_WHITE',
    'CL_OC_MEN_LINE52_BLACK',  # Print 5v1 SKU prefix
}

# Assemble verification (handles delayed state updates / async waybill creation)
ASSEMBLE_VERIFY_RETRIES = int(os.environ.get("KASPI_ASSEMBLE_VERIFY_RETRIES", "5"))
ASSEMBLE_VERIFY_DELAY = float(os.environ.get("KASPI_ASSEMBLE_VERIFY_DELAY", "3"))
ASSEMBLE_REFRESH_RETRIES = int(os.environ.get("KASPI_ASSEMBLE_REFRESH_RETRIES", "1"))
ASSEMBLE_REFRESH_DELAY = float(os.environ.get("KASPI_ASSEMBLE_REFRESH_DELAY", "10"))


@dataclass
class OrderItem:
    """Single order item from CRM."""
    order_id: str
    store_name: str
    kaspi_name_core: str
    my_size: str
    sku_key: str
    sku_id: str
    quantity: int
    planned_date: Optional[date]


def _coerce_str(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def load_db_order_info(
    db_path: Path,
    order_ids: Optional[set[str]] = None,
) -> dict[str, dict[str, Any]]:
    """Load assigned sizes and order details from DB (best-effort)."""
    if not db_path.exists():
        logger.warning(f"DB not found: {db_path}")
        return {}

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            logger.warning("DB missing fact_orders_kaspi; skipping DB sizes")
            return {}

        params: list[str] = []
        where_clause = ""
        if order_ids:
            placeholders = ",".join(["?"] * len(order_ids))
            where_clause = f"WHERE order_id IN ({placeholders})"
            params = list(order_ids)

        rows = conn.execute(
            f"""
            SELECT
                order_id,
                assigned_size,
                my_size,
                planned_shipment_date,
                store_code,
                kaspi_offer_name,
                sku_key,
                sku_id,
                quantity
            FROM fact_orders_kaspi
            {where_clause}
            """,
            params,
        ).fetchall()

    info: dict[str, dict[str, Any]] = {}
    for row in rows:
        order_id = _coerce_str(row["order_id"])
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id:
            continue
        size = _coerce_str(row["assigned_size"]) or _coerce_str(row["my_size"])
        planned_date = parse_date(row["planned_shipment_date"])
        info[order_id] = {
            "size": size,
            "planned_date": planned_date,
            "store_code": _coerce_str(row["store_code"]),
            "kaspi_offer_name": _coerce_str(row["kaspi_offer_name"]),
            "sku_key": _coerce_str(row["sku_key"]),
            "sku_id": _coerce_str(row["sku_id"]),
            "quantity": row["quantity"] if row["quantity"] is not None else 1,
        }

    return info


def resolve_db_path(explicit: Optional[Path]) -> Optional[Path]:
    if explicit:
        return explicit
    data_db = data_path("db", "app.db")
    if data_db.exists():
        return data_db
    if DEFAULT_DB_PATH.exists():
        return DEFAULT_DB_PATH
    return None


def parse_date(value: Any) -> Optional[date]:
    """Parse mixed CRM/DB date values without flipping ISO month/day order."""
    return parse_kaspi_date(value)


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


def normalize_store_name(value: Any) -> str:
    """Normalize store name from various formats."""
    if pd.isna(value) or not value:
        return "UNKNOWN"

    store_str = str(value).strip()

    # Direct match
    if store_str in STORE_MAP:
        return STORE_MAP[store_str]

    # API store code
    if store_str in API_CODE_TO_STORE_NAME:
        return API_CODE_TO_STORE_NAME[store_str]

    # Already a display name
    if store_str in STORE_NAME_TO_API_CODE:
        return store_str

    # Case-insensitive lookup
    for code, name in STORE_MAP.items():
        if code.lower() == store_str.lower() or name.lower() == store_str.lower():
            return name

    for api_code, display_name in API_CODE_TO_STORE_NAME.items():
        if api_code.lower() == store_str.lower():
            return display_name

    return store_str


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def is_heavy_item(item: OrderItem) -> bool:
    """Check if item is heavy (requires separate package)."""
    # Check against name core, sku_key, and sku_id
    checks = [item.kaspi_name_core, item.sku_key, item.sku_id]

    for check_value in checks:
        if not check_value:
            continue
        # Exact match
        if check_value in HEAVY_ITEMS:
            return True
        # Prefix match for SKU codes
        for heavy in HEAVY_ITEMS:
            if check_value.startswith(heavy):
                return True

    return False


def calculate_package_count(items: list[OrderItem]) -> int:
    """
    Calculate package count for an order based on heavy item logic.

    Rules:
    - Single item, qty=1 (NORMAL): 1 package
    - Single item, qty>1 (MULTI_QTY):
        - Heavy OR qty>3: qty packages (each item separate)
        - Otherwise: 1 package
    - Multiple items (MULTI_LINE):
        - Count heavy items (each gets own package)
        - Light items combine into 1 package (if any)
        - If total qty <= 3 and no heavy items: 1 package
    """
    if not items:
        return 1

    # Single line item
    if len(items) == 1:
        item = items[0]
        if item.quantity == 1:
            # NORMAL: always 1 package
            return 1
        else:
            # MULTI_QTY
            if is_heavy_item(item) or item.quantity > 3:
                return item.quantity
            else:
                return 1

    # Multiple line items (MULTI_LINE)
    heavy_count = sum(1 for item in items if is_heavy_item(item))
    light_count = len(items) - heavy_count
    total_qty = sum(item.quantity for item in items)

    if total_qty <= 3 and heavy_count == 0:
        return 1
    else:
        # Heavy items get separate packages, light items combine
        return heavy_count + (1 if light_count > 0 else 0)


def read_crm_orders(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    store_filter: Optional[str] = None,
    target_order_ids: Optional[set[str]] = None,
    db_order_info: Optional[dict[str, dict[str, Any]]] = None,
    apply_date_filter: bool = True,
    allow_missing_size: bool = True,
) -> dict[str, list[OrderItem]]:
    """
    Read orders from CRM Excel file, grouped by order_id.

    The shipping workflow must act only on sizes that were manually assigned in
    the current CRM batch view for the target date.

    Filters for orders where:
    - MY_SIZE is filled in CRM
    - planned_date <= target_date
    - Optionally filtered by store

    Returns dict: order_id -> list[OrderItem]
    """
    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    logger.info(f"Reading CRM from {crm_path}")
    df = pd.read_excel(crm_path, sheet_name=sheet_name)
    df, operational_stats = select_operational_crm_rows(
        df,
        target_date=target_date,
        order_id_filter=target_order_ids,
        allow_historical_fallback=False,
        backfill_overdue_my_size_from_history=True,
    )
    logger.info(
        "Resolved CRM current-batch rows: "
        f"orders={operational_stats['orders_selected']} "
        f"today={operational_stats['selected_today_orders']} "
        f"fallback={operational_stats['selected_fallback_orders']} "
        f"dropped_no_today={operational_stats['orders_without_today_row_dropped']} "
        f"historical_dropped={operational_stats['historical_rows_dropped']} "
        f"line_dupes_dropped={operational_stats['same_day_line_duplicates_dropped']} "
        f"overdue_size_backfilled={operational_stats['overdue_my_size_backfilled_rows']}"
    )

    orders_by_id: dict[str, list[OrderItem]] = defaultdict(list)
    skipped_no_size = 0
    missing_size_allowed = 0
    skipped_date = 0
    skipped_store = 0
    skipped_not_pending = 0
    used_crm_size = 0

    for _, row in df.iterrows():
        # Get order_id
        order_id = row.get('OrderID')
        if pd.isna(order_id):
            order_id = row.get('№ заказа')
        if pd.isna(order_id):
            continue

        order_id = str(order_id).strip()
        if order_id.endswith('.0'):
            order_id = order_id[:-2]

        if target_order_ids is not None and order_id not in target_order_ids:
            skipped_not_pending += 1
            continue

        db_info = db_order_info.get(order_id) if db_order_info else None
        # Check MY_SIZE from the current CRM batch only.
        my_size = str(row.get('MY_SIZE', '')).strip()
        if my_size.lower() in ('nan', 'none', ''):
            my_size = ""

        final_size = my_size
        if not final_size:
            if not allow_missing_size:
                skipped_no_size += 1
                continue
            missing_size_allowed += 1
            final_size = ""
        else:
            used_crm_size += 1

        # Get planned date
        planned_date = parse_date(row.get('PLANNED_SHIPPING_DATE'))
        if not planned_date:
            planned_date = parse_date(row.get('Плановая дата передачи курьеру'))
        if not planned_date and db_info:
            planned_date = db_info.get("planned_date")

        # Filter by date - skip future orders (unless API already filtered)
        if apply_date_filter and planned_date and planned_date > target_date:
            skipped_date += 1
            continue

        # Get store name
        store_name = row.get('STORE_NAME')
        if pd.isna(store_name):
            store_name = row.get('Склад передачи КД')
        store_name = normalize_store_name(store_name)

        # Filter by store if specified
        if store_filter and store_name != store_filter:
            skipped_store += 1
            continue

        # Get other fields
        kaspi_name_core = str(row.get('Kaspi_name_core', '')).strip()
        if not kaspi_name_core or kaspi_name_core.lower() == 'nan':
            kaspi_offer = str(row.get('KASPI_OFFER_NAME', '')).strip()
            if kaspi_offer.lower() == 'nan':
                kaspi_offer = ""
            kaspi_name_core = extract_name_core(kaspi_offer) if kaspi_offer else ""

        sku_key = str(row.get('SKU_key', '')).strip()
        if sku_key.lower() == 'nan':
            sku_key = ""

        sku_id = str(row.get('SKU_ID', '')).strip()
        if sku_id.lower() == 'nan':
            sku_id = ""

        quantity = int(row.get('Quantity', 1)) if not pd.isna(row.get('Quantity')) else 1

        item = OrderItem(
            order_id=order_id,
            store_name=store_name,
            kaspi_name_core=kaspi_name_core,
            my_size=final_size,
            sku_key=sku_key,
            sku_id=sku_id,
            quantity=quantity,
            planned_date=planned_date,
        )
        orders_by_id[order_id].append(item)

    if allow_missing_size:
        logger.info(
            f"Read {len(orders_by_id)} unique orders (missing size allowed: {missing_size_allowed})"
        )
    else:
        logger.info(f"Read {len(orders_by_id)} unique orders with MY_SIZE filled")
    if skipped_no_size:
        logger.info(f"Skipped {skipped_no_size} rows without MY_SIZE")
    if apply_date_filter:
        logger.info(f"Skipped {skipped_date} rows with future planned date")
    logger.info(f"Used CRM sizes: {used_crm_size}")
    if store_filter:
        logger.info(f"Skipped {skipped_store} rows from other stores")
    if target_order_ids is not None:
        logger.info(f"Skipped {skipped_not_pending} rows not in pending assembly list")

    return dict(orders_by_id)


def read_db_orders(
    db_path: Path,
    target_date: date,
    *,
    store_filter: Optional[str] = None,
    target_order_ids: Optional[set[str]] = None,
    apply_date_filter: bool = True,
    allow_missing_size: bool = False,
) -> dict[str, list[OrderItem]]:
    """
    Read orders from fact_orders_kaspi (DB-first), grouped by order_id.

    This is the automated closeout path. It uses DB size truth
    (assigned_size first, then my_size) and does not depend on the CRM workbook.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}")

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            raise RuntimeError("DB missing fact_orders_kaspi table")

        params: list[Any] = []
        where_parts = ["planned_shipment_date <= ?"]
        params.append(target_date.isoformat())
        if target_order_ids:
            placeholders = ",".join("?" for _ in target_order_ids)
            where_parts.append(f"order_id IN ({placeholders})")
            params.extend(sorted(target_order_ids))

        rows = conn.execute(
            f"""
            SELECT
                order_id,
                store_code,
                kaspi_offer_name,
                sku_key,
                sku_id,
                quantity,
                assigned_size,
                my_size,
                planned_shipment_date
            FROM fact_orders_kaspi
            WHERE {' AND '.join(where_parts)}
            ORDER BY planned_shipment_date, order_id, id
            """,
            params,
        ).fetchall()

    orders_by_id: dict[str, list[OrderItem]] = defaultdict(list)
    skipped_no_size = 0
    skipped_date = 0
    skipped_store = 0

    for row in rows:
        order_id = _coerce_str(row["order_id"])
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id:
            continue

        planned_date = parse_date(row["planned_shipment_date"])
        if apply_date_filter and planned_date and planned_date > target_date:
            skipped_date += 1
            continue

        store_name = normalize_store_name(row["store_code"])
        if store_filter and store_name != store_filter:
            skipped_store += 1
            continue

        final_size = _coerce_str(row["assigned_size"]) or _coerce_str(row["my_size"])
        if not final_size and not allow_missing_size:
            skipped_no_size += 1
            continue

        kaspi_offer_name = _coerce_str(row["kaspi_offer_name"])
        kaspi_name_core = extract_name_core(kaspi_offer_name) if kaspi_offer_name else ""
        if not kaspi_name_core or kaspi_name_core.lower() == "unknown":
            kaspi_name_core = _coerce_str(row["sku_key"]) or _coerce_str(row["sku_id"]) or "UNKNOWN"

        quantity = int(row["quantity"] or 1)
        item = OrderItem(
            order_id=order_id,
            store_name=store_name,
            kaspi_name_core=kaspi_name_core,
            my_size=final_size,
            sku_key=_coerce_str(row["sku_key"]),
            sku_id=_coerce_str(row["sku_id"]),
            quantity=quantity,
            planned_date=planned_date,
        )
        orders_by_id[order_id].append(item)

    logger.info(
        "Read %s unique orders from DB%s",
        len(orders_by_id),
        " (missing size allowed)" if allow_missing_size else " with assigned/manual size",
    )
    if skipped_no_size:
        logger.info(f"Skipped {skipped_no_size} DB rows without assigned/manual size")
    if apply_date_filter:
        logger.info(f"Skipped {skipped_date} DB rows with future planned date")
    if store_filter:
        logger.info(f"Skipped {skipped_store} DB rows from other stores")

    return dict(orders_by_id)


def _creation_dt_from_order(order: dict) -> Optional[datetime]:
    """Extract order creation datetime from Kaspi API payload."""
    ts = order.get("attributes", {}).get("creationDate")
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts) / 1000, tz=ALMATY_TZ).replace(tzinfo=None)
    except (ValueError, OSError, TypeError):
        return None


def _extract_orders_from_list_response(response: Any) -> tuple[list[dict], Optional[int]]:
    """Normalize API list response shape to orders + optional page count."""
    if isinstance(response, APIResponse):
        if not response.success:
            return [], None
        payload = response.data or {}
    else:
        payload = response or {}
    data = payload.get("data") or []
    meta = payload.get("meta") or {}
    page_count = meta.get("pageCount")
    return data, int(page_count) if page_count else None


def _response_requires_since(response: Any) -> bool:
    """Detect Kaspi API validation error requiring creationDate[$ge]."""
    if not isinstance(response, APIResponse):
        return False
    if response.success:
        return False
    err_text = str(response.error or "")
    return "creationDate" in err_text and "$ge" in err_text


def get_pending_assembly_orders(
    target_date: Optional[date] = None,
    since_days: Optional[int] = 7,
    *,
    store_codes: Optional[set[str]] = None,
    fallback_since_days: int = 30,
    include_overdue: bool = False,
    overdue_lookback_days: Optional[int] = None,
) -> tuple[
    dict[str, set[str]],
    dict[str, dict[str, str]],
    dict[str, dict[str, date]],
    dict[str, dict[str, dict[str, Any]]],
]:
    """
    Get orders in "Упаковка" stage from ALL stores via API.

    Returns:
        - pending_by_store: dict store_api_code -> set of order_ids pending assembly
        - order_id_to_base64: dict store_code -> {order_code: base64_id}
        - planned_by_store: dict store_api_code -> {order_code: planned_date}
        - pending_meta_by_store: dict store_api_code -> order metadata
    """
    pending_by_store: dict[str, set[str]] = {}
    # Store-scoped base64 IDs prevent cross-store collisions on assemble.
    order_id_to_base64: dict[str, dict[str, str]] = {}
    planned_by_store: dict[str, dict[str, date]] = {}
    pending_meta_by_store: dict[str, dict[str, dict[str, Any]]] = {}

    since = None
    if since_days is not None:
        since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')

    scope = set(store_codes or STORE_TOKEN_MAP.keys())
    for store_code in STORE_TOKEN_MAP.keys():
        if store_code not in scope:
            continue
        try:
            client = KaspiAPIClient(store_code=store_code)
            fetch_mode = "status-first"
            orders: list[dict] = []

            page_number = 0
            while True:
                response = client.list_orders(
                    state="KASPI_DELIVERY",
                    status="ACCEPTED_BY_MERCHANT",
                    since=since,
                    page_number=page_number,
                    page_size=100,
                )
                if _response_requires_since(response) and since is None:
                    fetch_mode = f"fallback-creation-lookback-{fallback_since_days}d"
                    fallback_since = (
                        datetime.now(ALMATY_TZ) - timedelta(days=fallback_since_days)
                    ).strftime("%Y-%m-%d")
                    fallback_result = client.get_pending_assembly_orders(since=fallback_since)
                    if fallback_result.success:
                        orders = fallback_result.data.get("data", [])
                    else:
                        logger.warning(
                            f"{store_code}: Could not fetch pending orders: {fallback_result.error}"
                        )
                        orders = []
                    break
                if isinstance(response, APIResponse) and not response.success:
                    logger.warning(f"{store_code}: Could not fetch pending orders: {response.error}")
                    orders = []
                    break

                page_orders, page_count = _extract_orders_from_list_response(response)
                if not page_orders:
                    break
                orders.extend(page_orders)
                page_number += 1
                if page_count is not None and page_number >= page_count:
                    break

            order_ids = set()
            for order in orders:
                attrs = order.get("attributes", {})
                if attrs.get("assembled"):
                    continue
                order_code = attrs.get("code", "")
                base64_id = order.get("id", "")
                planned_date = _planned_date_from_order(order)
                if target_date:
                    if include_overdue:
                        min_date: Optional[date] = None
                        if overdue_lookback_days is not None:
                            min_date = target_date - timedelta(days=max(int(overdue_lookback_days), 0))
                        if (
                            planned_date is None
                            or planned_date > target_date
                            or (min_date is not None and planned_date < min_date)
                        ):
                            continue
                    elif planned_date != target_date:
                        continue
                if order_code:
                    order_ids.add(order_code)
                    if base64_id:
                        order_id_to_base64.setdefault(store_code, {})[order_code] = base64_id
                    if planned_date:
                        planned_by_store.setdefault(store_code, {})[order_code] = planned_date
                    pending_meta_by_store.setdefault(store_code, {})[order_code] = {
                        "planned_date": planned_date,
                        "created_at": _creation_dt_from_order(order),
                        "fetch_mode": fetch_mode,
                    }
            pending_by_store[store_code] = order_ids
            logger.info(f"{store_code}: {len(order_ids)} orders pending assembly")
        except KaspiAuthError as e:
            logger.warning(f"{store_code}: Auth error - {e}")
            pending_by_store[store_code] = set()

    return pending_by_store, order_id_to_base64, planned_by_store, pending_meta_by_store


def summarize_pending_backlog(
    pending_meta_by_store: dict[str, dict[str, dict[str, Any]]],
    target_date: date,
    stale_hours: int = 24,
    now_dt: Optional[datetime] = None,
) -> dict[str, Any]:
    """Summarize pending backlog health for alerts/telemetry."""
    now_dt = now_dt or datetime.now(ALMATY_TZ).replace(tzinfo=None)
    total_pending = 0
    overdue_pending = 0
    stale_pending = 0
    stale_orders: list[dict[str, Any]] = []

    for store_code, store_rows in pending_meta_by_store.items():
        for order_id, meta in store_rows.items():
            total_pending += 1
            planned_date = meta.get("planned_date")
            created_at = meta.get("created_at")
            if isinstance(planned_date, date) and planned_date < now_dt.date():
                overdue_pending += 1
            if isinstance(created_at, datetime):
                age_hours = (now_dt - created_at).total_seconds() / 3600
                if age_hours >= stale_hours:
                    stale_pending += 1
                    stale_orders.append(
                        {
                            "store_code": store_code,
                            "order_id": order_id,
                            "planned_date": planned_date,
                            "created_at": created_at.isoformat(sep=" "),
                            "age_hours": round(age_hours, 1),
                        }
                    )

    stale_orders.sort(key=lambda row: row["age_hours"], reverse=True)
    return {
        "total_pending": total_pending,
        "overdue_pending": overdue_pending,
        "stale_pending": stale_pending,
        "stale_orders": stale_orders,
    }


def print_pending_backlog(label: str, backlog: dict[str, Any]) -> None:
    """Emit a compact backlog summary with a small stale-order sample."""
    print(f"\n{label}")
    print(
        "  Pending backlog: "
        f"total={backlog.get('total_pending', 0)} "
        f"overdue={backlog.get('overdue_pending', 0)} "
        f"stale={backlog.get('stale_pending', 0)}"
    )
    stale_orders = backlog.get("stale_orders") or []
    if stale_orders:
        print("  Oldest stale pending orders:")
        for row in stale_orders[:5]:
            planned = row.get("planned_date") or "unknown"
            created_at = row.get("created_at") or "unknown"
            age_hours = row.get("age_hours")
            print(
                f"    - {row.get('store_code')} {row.get('order_id')} | "
                f"planned={planned} | created={created_at} | age_hours={age_hours}"
            )
        if len(stale_orders) > 5:
            print(f"    ... and {len(stale_orders) - 5} more")


def _serialize_backlog_date(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return None


def _overdue_age_bucket(days_overdue: int) -> str:
    if days_overdue <= 1:
        return "1d"
    if days_overdue <= 3:
        return "2-3d"
    if days_overdue <= 7:
        return "4-7d"
    return "8d+"


def build_pending_backlog_report(
    pending_meta_by_store: dict[str, dict[str, dict[str, Any]]],
    *,
    target_date: date,
    stale_hours: int = 24,
    now_dt: Optional[datetime] = None,
) -> dict[str, Any]:
    """Build a detailed backlog payload with age buckets and exact overdue IDs."""
    now_dt = now_dt or datetime.now(ALMATY_TZ).replace(tzinfo=None)
    summary = summarize_pending_backlog(
        pending_meta_by_store=pending_meta_by_store,
        target_date=target_date,
        stale_hours=stale_hours,
        now_dt=now_dt,
    )
    age_buckets: dict[str, int] = defaultdict(int)
    pending_rows: list[dict[str, Any]] = []
    overdue_rows: list[dict[str, Any]] = []

    for store_code in sorted(pending_meta_by_store):
        store_rows = pending_meta_by_store.get(store_code) or {}
        for order_id in sorted(store_rows):
            meta = store_rows.get(order_id) or {}
            planned_date = meta.get("planned_date")
            created_at = meta.get("created_at")
            days_overdue = None
            if isinstance(planned_date, date):
                days_overdue = max((now_dt.date() - planned_date).days, 0)
            age_hours = None
            if isinstance(created_at, datetime):
                age_hours = round((now_dt - created_at).total_seconds() / 3600, 1)
            row = {
                "store_code": store_code,
                "order_id": order_id,
                "planned_date": _serialize_backlog_date(planned_date),
                "created_at": _serialize_backlog_date(created_at),
                "days_overdue": days_overdue,
                "age_hours": age_hours,
                "fetch_mode": meta.get("fetch_mode"),
            }
            pending_rows.append(row)
            if days_overdue and days_overdue > 0:
                age_buckets[_overdue_age_bucket(days_overdue)] += 1
                overdue_rows.append(row)

    overdue_rows.sort(
        key=lambda row: (
            -(row.get("days_overdue") or 0),
            -(row.get("age_hours") or 0.0),
            row.get("store_code") or "",
            row.get("order_id") or "",
        )
    )
    return {
        "generated_at": now_dt.isoformat(sep=" "),
        "target_date": target_date.isoformat(),
        "stale_hours": stale_hours,
        "summary": summary,
        "age_buckets": dict(age_buckets),
        "pending_orders": pending_rows,
        "overdue_orders": overdue_rows,
    }


def _render_pending_backlog_report_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Pending Assembly Backlog Report",
        "",
        f"- Generated: {payload.get('generated_at')}",
        f"- Target date: {payload.get('target_date')}",
        f"- Scope: {payload.get('store_scope')}",
        f"- Mode: {'DRY_RUN' if payload.get('dry_run') else 'LIVE'}",
        f"- Include overdue: {payload.get('include_overdue')}",
        f"- Overdue lookback days: {payload.get('overdue_lookback_days')}",
        "",
    ]
    for label, section in (("Initial", payload.get("initial")), ("Remaining", payload.get("remaining"))):
        if not section:
            continue
        summary = section.get("summary") or {}
        lines.extend(
            [
                f"## {label} Snapshot",
                "",
                f"- Total pending: {summary.get('total_pending', 0)}",
                f"- Overdue pending: {summary.get('overdue_pending', 0)}",
                f"- Stale pending: {summary.get('stale_pending', 0)}",
            ]
        )
        age_buckets = section.get("age_buckets") or {}
        if age_buckets:
            lines.append(f"- Overdue age buckets: {json.dumps(age_buckets, ensure_ascii=False, sort_keys=True)}")
        lines.extend(["", "### Exact Pending Orders", ""])
        pending_rows = section.get("pending_orders") or []
        if pending_rows:
            lines.extend(
                [
                    "| Store | Order ID | Planned | Days Overdue | Created | Age Hours | Fetch Mode |",
                    "|---|---|---|---:|---|---:|---|",
                ]
            )
            for row in pending_rows:
                lines.append(
                    "| {store} | {order} | {planned} | {days} | {created} | {hours} | {mode} |".format(
                        store=row.get("store_code") or "",
                        order=row.get("order_id") or "",
                        planned=row.get("planned_date") or "",
                        days=row.get("days_overdue") or 0,
                        created=row.get("created_at") or "",
                        hours=row.get("age_hours") or 0,
                        mode=row.get("fetch_mode") or "",
                    )
                )
        else:
            lines.append("None.")
        lines.extend(["", "### Exact Overdue Orders", ""])
        overdue_rows = section.get("overdue_orders") or []
        if overdue_rows:
            lines.extend(
                [
                    "| Store | Order ID | Planned | Days Overdue | Created | Age Hours | Fetch Mode |",
                    "|---|---|---|---:|---|---:|---|",
                ]
            )
            for row in overdue_rows:
                lines.append(
                    "| {store} | {order} | {planned} | {days} | {created} | {hours} | {mode} |".format(
                        store=row.get("store_code") or "",
                        order=row.get("order_id") or "",
                        planned=row.get("planned_date") or "",
                        days=row.get("days_overdue") or 0,
                        created=row.get("created_at") or "",
                        hours=row.get("age_hours") or 0,
                        mode=row.get("fetch_mode") or "",
                    )
                )
        else:
            lines.append("None.")
        lines.extend(["", "### Exact Stale Orders", ""])
        stale_rows = summary.get("stale_orders") or []
        if stale_rows:
            lines.extend(
                [
                    "| Store | Order ID | Planned | Created | Age Hours |",
                    "|---|---|---|---|---:|",
                ]
            )
            for row in stale_rows:
                lines.append(
                    "| {store} | {order} | {planned} | {created} | {hours} |".format(
                        store=row.get("store_code") or "",
                        order=row.get("order_id") or "",
                        planned=row.get("planned_date") or "",
                        created=row.get("created_at") or "",
                        hours=row.get("age_hours") or 0,
                    )
                )
        else:
            lines.append("None.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_pending_backlog_report(
    *,
    target_date: date,
    store_scope: str,
    dry_run: bool,
    include_overdue: bool,
    overdue_lookback_days: Optional[int],
    initial_report: dict[str, Any],
    remaining_report: Optional[dict[str, Any]] = None,
    output_root: Optional[Path] = None,
) -> tuple[Path, Path]:
    """Write JSON + Markdown backlog reports for audit visibility."""
    timestamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    base_dir = output_root or data_path("reports", "kaspi_pending_backlog", target_date.isoformat())
    base_dir.mkdir(parents=True, exist_ok=True)
    scope_slug = (store_scope or "ALL_STORES").replace("-", "_").replace(" ", "_")
    payload = {
        "generated_at": datetime.now(ALMATY_TZ).isoformat(sep=" "),
        "target_date": target_date.isoformat(),
        "store_scope": store_scope or "ALL_STORES",
        "dry_run": dry_run,
        "include_overdue": include_overdue,
        "overdue_lookback_days": overdue_lookback_days,
        "initial": initial_report,
        "remaining": remaining_report,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    json_path = base_dir / f"ship_orders_backlog_{scope_slug}_{timestamp}.json"
    md_path = base_dir / f"ship_orders_backlog_{scope_slug}_{timestamp}.md"
    json_path.write_text(payload_json, encoding="utf-8")
    md_path.write_text(_render_pending_backlog_report_md(payload), encoding="utf-8")
    latest_json = base_dir / f"ship_orders_backlog_{scope_slug}_latest.json"
    latest_md = base_dir / f"ship_orders_backlog_{scope_slug}_latest.md"
    latest_json.write_text(payload_json, encoding="utf-8")
    latest_md.write_text(_render_pending_backlog_report_md(payload), encoding="utf-8")
    return json_path, md_path


def derive_dynamic_since_days(
    db_path: Path,
    target_date: date,
    store_codes: Optional[set[str]] = None,
    default_days: int = 14,
    max_days: int = 120,
) -> int:
    """Derive safe creation-date lookback based on oldest pending record in DB."""
    if not db_path or not Path(db_path).exists():
        return default_days

    scope = set(store_codes or [])
    with get_db(Path(db_path)) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            return default_days
        rows = conn.execute(
            """
            SELECT store_code, planned_shipment_date, created_at
            FROM fact_orders_kaspi
            WHERE kaspi_status = 'KASPI_DELIVERY'
              AND (internal_status IS NULL OR internal_status NOT IN ('SHIPPED', 'COMPLETED', 'CANCELLED'))
            """
        ).fetchall()

    oldest_days = default_days
    for row in rows:
        store = _coerce_str(row["store_code"]).upper()
        if scope and store and store not in scope:
            continue
        planned_raw = _coerce_str(row["planned_shipment_date"])
        planned = parse_date(planned_raw) if planned_raw else None
        if planned and planned > target_date:
            continue
        created_raw = _coerce_str(row["created_at"])
        if not created_raw:
            continue
        try:
            created_dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if created_dt.tzinfo is not None:
                created_dt = created_dt.astimezone(ALMATY_TZ).replace(tzinfo=None)
        except ValueError:
            continue
        age_days = max(0, (target_date - created_dt.date()).days + 1)
        oldest_days = max(oldest_days, age_days)

    return min(max_days, oldest_days)


def ship_orders(
    orders_by_id: dict[str, list[OrderItem]],
    pending_orders: dict[str, set[str]],
    order_id_to_base64: dict[str, dict[str, str]],
    dry_run: bool = False,
    verbose: bool = False,
    since_days: int = 7,
) -> dict:
    """
    Ship orders via Kaspi API.

    For each order that is in pending_orders (Упаковка stage):
    1. Calculate package count
    2. Call assemble_order_by_id(base64_id, order_code, parcel_count)

    Args:
        orders_by_id: dict order_id -> list[OrderItem]
        pending_orders: dict store_api_code -> set of order_ids pending
        order_id_to_base64: dict store_code -> {order_code: base64_id}

    Returns summary dict with counts.
    """
    shipped = 0
    skipped = 0
    already_shipped = 0
    errors = []

    # Flatten pending orders for quick lookup
    all_pending = set()
    for order_ids in pending_orders.values():
        all_pending.update(order_ids)


    # Group orders by store for API client management
    orders_by_store: dict[str, dict[str, list[OrderItem]]] = defaultdict(dict)
    for order_id, items in orders_by_id.items():
        # Skip orders not in pending assembly
        if order_id not in all_pending:
            already_shipped += 1
            continue
        store_name = items[0].store_name
        orders_by_store[store_name][order_id] = items

    if already_shipped > 0:
        logger.info(f"Skipped {already_shipped} orders already shipped/not in Упаковка")

    for store_name, store_orders in orders_by_store.items():
        # Get API store code
        api_store_code = STORE_NAME_TO_API_CODE.get(store_name)
        if not api_store_code:
            logger.warning(f"Unknown store: {store_name}, skipping {len(store_orders)} orders")
            skipped += len(store_orders)
            continue

        # Initialize API client for this store
        try:
            client = KaspiAPIClient(store_code=api_store_code)
        except KaspiAuthError as e:
            logger.error(f"Auth error for {store_name}: {e}")
            errors.append(f"{store_name}: Auth error")
            skipped += len(store_orders)
            continue

        print(f"\n  Processing {store_name} ({len(store_orders)} orders)...")
        retry_queue: dict[str, int] = {}

        for order_id, items in store_orders.items():
            # Calculate package count
            parcel_count = calculate_package_count(items)

            if verbose:
                item_desc = ", ".join(f"{i.kaspi_name_core}x{i.quantity}" for i in items)
                heavy_mark = " [HEAVY]" if any(is_heavy_item(i) for i in items) else ""
                print(f"    {order_id}: {parcel_count} pkg ({item_desc}){heavy_mark}")

            if dry_run:
                shipped += 1
                continue

            def _is_assembled_now(order_code: str, base64_hint: Optional[str] = None) -> bool:
                try:
                    if base64_hint and hasattr(client, "get_order_by_id"):
                        detail = client.get_order_by_id(base64_hint)
                        if detail.success:
                            attrs = detail.data.get('attributes', {})
                            if attrs.get('assembled') is True or client.get_waybill_url(detail.data):
                                return True
                except Exception:
                    pass
                try:
                    detail = client.get_order(order_code)
                    if detail.success:
                        attrs = detail.data.get('attributes', {})
                        if attrs.get('assembled') is True or client.get_waybill_url(detail.data):
                            return True
                except Exception:
                    pass
                return False

            # Helper: verify assemble state (handles delayed state updates)
            def _wait_for_assembled(order_code: str, base64_hint: Optional[str] = None) -> bool:
                for attempt in range(ASSEMBLE_VERIFY_RETRIES):
                    if _is_assembled_now(order_code, base64_hint):
                        if verbose:
                            print("      -> Assembled confirmed")
                        return True
                    if attempt < ASSEMBLE_VERIFY_RETRIES - 1:
                        time.sleep(ASSEMBLE_VERIFY_DELAY)
                return False

            def _queue_retry(order_code: str, parcels: int) -> None:
                retry_queue.setdefault(order_code, parcels)
                if verbose:
                    print("      -> Queued for retry (refresh pending list)")

            def _fallback_assemble(reason: str, base64_hint: Optional[str] = None) -> bool:
                if verbose:
                    print(f"      -> WARN: {reason}. Retrying with order code...")
                try:
                    result_fallback = client.assemble_order(order_id, parcel_count=parcel_count)
                    if result_fallback.success:
                        if _wait_for_assembled(order_id, base64_hint):
                            if verbose:
                                print("      -> Shipped OK (fallback)")
                            return True
                        _queue_retry(order_id, parcel_count)
                        return False
                    err_text = str(result_fallback.error or "")
                    if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                        if _wait_for_assembled(order_id, base64_hint):
                            return True
                        _queue_retry(order_id, parcel_count)
                        return False
                    errors.append(f"{order_id}: API error - {result_fallback.error} (fallback)")
                    if verbose:
                        print(f"      -> ERROR: {result_fallback.error} (fallback)")
                except Exception as exc:
                    if "not found" in str(exc).lower() or "resource not found" in str(exc).lower():
                        if _wait_for_assembled(order_id, base64_hint):
                            return True
                        _queue_retry(order_id, parcel_count)
                        return False
                    errors.append(f"{order_id}: {str(exc)} (fallback)")
                    if verbose:
                        print(f"      -> EXCEPTION: {exc} (fallback)")
                return False

            # Get Base64 ID from pre-fetched mapping (store-specific)
            base64_id = order_id_to_base64.get(api_store_code, {}).get(order_id)
            if not base64_id:
                # If missing, fallback to direct lookup by order code.
                if _fallback_assemble("No Base64 ID found (state changed?)"):
                    shipped += 1
                continue

            # Call API with pre-fetched Base64 ID (avoids re-fetch 404)
            try:
                result = client.assemble_order_by_id(base64_id, order_id, parcel_count=parcel_count)
                if result.success:
                    if _is_assembled_now(order_id, base64_id):
                        shipped += 1
                        if verbose:
                            print("      -> Shipped OK")
                    elif _fallback_assemble("Assemble accepted but not confirmed", base64_id):
                        shipped += 1
                    else:
                        _queue_retry(order_id, parcel_count)
                else:
                    # Some API errors return 404-equivalent errors without raising.
                    err_text = str(result.error or "")
                    if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                        if _wait_for_assembled(order_id, base64_id):
                            shipped += 1
                            continue
                        _queue_retry(order_id, parcel_count)
                        continue
                    errors.append(f"{order_id}: API error - {result.error}")
                    if verbose:
                        print(f"      -> ERROR: {result.error}")
            except KaspiNotFoundError as e:
                # Retry with direct lookup if base64 ID is stale or mismatched.
                if _fallback_assemble(str(e), base64_id):
                    shipped += 1
            except KaspiWriteDisabledError:
                logger.error("Write operations disabled. Set ENABLE_KASPI_WRITE=1 in .env")
                return {
                    'shipped': 0,
                    'skipped': len(orders_by_id),
                    'errors': ['Write operations disabled'],
                }
            except Exception as e:
                # Unknown exception: try fallback once, then record error.
                if _fallback_assemble(str(e), base64_id):
                    shipped += 1
                else:
                    errors.append(f"{order_id}: {str(e)}")
                    if verbose:
                        print(f"      -> EXCEPTION: {e}")

        if retry_queue and ASSEMBLE_REFRESH_RETRIES > 0:
            refresh_since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')
            if verbose:
                print(f"  Retrying {len(retry_queue)} orders after refresh...")
            for attempt in range(ASSEMBLE_REFRESH_RETRIES):
                if ASSEMBLE_REFRESH_DELAY > 0:
                    time.sleep(ASSEMBLE_REFRESH_DELAY)
                refreshed = client.get_pending_assembly_orders(since=refresh_since)
                if not refreshed.success:
                    errors.append(f"{store_name}: refresh pending failed - {refreshed.error}")
                    break
                refreshed_map: dict[str, str] = {}
                for order in refreshed.data.get('data', []):
                    order_code = order.get('attributes', {}).get('code', '')
                    if not order_code:
                        continue
                    base64_id = order.get('id', '')
                    if base64_id:
                        refreshed_map[order_code] = base64_id
                still_retry: dict[str, int] = {}
                for order_code, parcels in retry_queue.items():
                    base64_id = refreshed_map.get(order_code)
                    if not base64_id:
                        if _wait_for_assembled(order_code):
                            shipped += 1
                            continue
                        still_retry[order_code] = parcels
                        continue
                    result = client.assemble_order_by_id(base64_id, order_code, parcel_count=parcels)
                    if result.success:
                        if _is_assembled_now(order_code, base64_id):
                            shipped += 1
                            if verbose:
                                print(f"      {order_code}: Shipped OK (refresh)")
                        else:
                            still_retry[order_code] = parcels
                        continue
                    err_text = str(result.error or "")
                    if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                        if _wait_for_assembled(order_code, base64_id):
                            shipped += 1
                            continue
                        still_retry[order_code] = parcels
                        continue
                    errors.append(f"{order_code}: API error - {result.error} (refresh)")
                    if verbose:
                        print(f"      {order_code}: ERROR - {result.error} (refresh)")
                retry_queue = still_retry
                if not retry_queue:
                    break
            if retry_queue:
                for order_code in retry_queue:
                    errors.append(f"{order_code}: Assemble not confirmed after refresh")
        elif retry_queue:
            for order_code in retry_queue:
                errors.append(f"{order_code}: Assemble not confirmed (refresh disabled)")

    return {
        'shipped': shipped,
        'skipped': skipped,
        'errors': errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ship Kaspi orders - set package count and move to 'Передача'"
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
        choices=['AcmeWear', 'Universal', '11KZ', 'STORE-B', 'Store-C'],
        help='Filter by store (optional)'
    )
    parser.add_argument(
        '--date',
        help='Target date (default: today, format: YYYY-MM-DD)'
    )
    parser.add_argument(
        '--since-days',
        type=int,
        default=7,
        help='Days to look back in API (default: 7)'
    )
    parser.add_argument(
        '--include-overdue',
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            'Include overdue pending assembly orders within --overdue-lookback-days '
            '(default: on). Use --no-include-overdue or --today-only for strict '
            'current-day only mode.'
        ),
    )
    parser.add_argument(
        '--today-only',
        action='store_true',
        help='Strict current-day mode: exclude overdue pending assembly orders.',
    )
    parser.add_argument(
        '--overdue-lookback-days',
        type=int,
        default=None,
        help='Lookback window for overdue carry-forward. Defaults to --since-days when omitted.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview only, do not call API'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--allow-missing-size',
        action='store_true',
        help='Allow assembling pending orders even if size is missing'
    )
    parser.add_argument(
        '--selection-source',
        choices=['crm', 'db'],
        default='crm',
        help='Selection source for package-count shipping: crm (manual fallback) or db (automated closeout path)'
    )
    parser.add_argument(
        '--json-out',
        type=Path,
        default=None,
        help='Optional JSON output path for shipping summary'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(ALMATY_TZ).date()
    include_overdue = bool(args.include_overdue) and not bool(args.today_only)
    overdue_lookback_days = args.overdue_lookback_days
    if include_overdue and overdue_lookback_days is None:
        overdue_lookback_days = args.since_days

    print("=" * 60)
    print("  Kaspi Order Shipping (Set Package Count)")
    print("=" * 60)
    print(f"  Data root: {get_data_root()}")
    print(f"  CRM file: {args.crm_file}")
    print(f"  Target date: {target_date}")
    print(f"  Selection source: {args.selection_source}")
    if include_overdue:
        lookback_label = overdue_lookback_days if overdue_lookback_days is not None else "all"
        print(f"  Date mode: planned <= target (lookback {lookback_label}d)")
    else:
        print("  Date mode: planned == target only")
    if args.store:
        print(f"  Store filter: {args.store}")
    if args.dry_run:
        print("  [DRY RUN MODE - No API calls]")
    print()

    # Step 1: Get pending assembly orders from API
    print("Step 1: Fetching pending assembly orders from API...")
    selected_store_codes: Optional[set[str]] = None
    if args.store:
        selected_code = STORE_NAME_TO_API_CODE.get(args.store, args.store.upper())
        selected_store_codes = {selected_code}
    pending_orders, order_id_to_base64, _planned_map, pending_meta = get_pending_assembly_orders(
        target_date=target_date,
        since_days=args.since_days,
        store_codes=selected_store_codes,
        include_overdue=include_overdue,
        overdue_lookback_days=overdue_lookback_days,
    )

    total_pending = sum(len(ids) for ids in pending_orders.values())
    if total_pending == 0:
        print("No orders pending assembly in Kaspi (Упаковка stage).")
        return 0

    print(f"  Found {total_pending} orders pending assembly across all stores")
    initial_backlog = build_pending_backlog_report(
        pending_meta,
        target_date=target_date,
    )
    print_pending_backlog("  Initial backlog snapshot...", initial_backlog["summary"])

    all_pending = set()
    for order_ids in pending_orders.values():
        all_pending.update(order_ids)
    pending_store_for_order: dict[str, str] = {}
    for store_code, order_ids in pending_orders.items():
        for order_id in order_ids:
            pending_store_for_order[order_id] = store_code

    # Step 2: Read orders from CRM
    resolved_db_path = resolve_db_path(args.db_path)
    if resolved_db_path:
        print(f"  DB: {resolved_db_path}")
    db_order_info = load_db_order_info(resolved_db_path or DEFAULT_DB_PATH, all_pending)
    if args.selection_source == "db":
        print("\nStep 2: Reading DB-assigned sizes for automated closeout...")
        if not resolved_db_path:
            raise RuntimeError("DB-first shipping requires a resolved db/app.db path")
        orders_by_id = read_db_orders(
            resolved_db_path,
            target_date,
            store_filter=args.store,
            target_order_ids=all_pending,
            apply_date_filter=False,
            allow_missing_size=args.allow_missing_size,
        )
    else:
        print("\nStep 2: Reading CRM for manually assigned MY_SIZE data...")
        orders_by_id = read_crm_orders(
            args.crm_file,
            args.sheet,
            target_date,
            store_filter=args.store,
            target_order_ids=all_pending,
            db_order_info=db_order_info,
            apply_date_filter=False,
            allow_missing_size=args.allow_missing_size,
        )

    # Add placeholder orders missing in the current CRM batch only when
    # allow_missing_size is explicitly enabled. Never reintroduce DB sizes as
    # actionable size truth for operator shipping.
    missing_in_selection = all_pending - set(orders_by_id.keys())
    added_missing_crm_placeholders = 0
    skipped_missing_current_crm = 0
    skipped_placeholder_store = 0
    added_api_only = 0
    if missing_in_selection:
        for order_id in missing_in_selection:
            info = db_order_info.get(order_id)
            if not args.allow_missing_size:
                skipped_missing_current_crm += 1
                continue
            if not info:
                store_code = pending_store_for_order.get(order_id)
                if args.store:
                    expected_code = STORE_NAME_TO_API_CODE.get(args.store, args.store)
                    if store_code and store_code != expected_code:
                        skipped_placeholder_store += 1
                        continue
                store_name = API_CODE_TO_STORE_NAME.get(store_code or "", store_code or "UNKNOWN")
                item = OrderItem(
                    order_id=order_id,
                    store_name=store_name,
                    kaspi_name_core="UNKNOWN",
                    my_size="",
                    sku_key="",
                    sku_id="",
                    quantity=1,
                    planned_date=None,
                )
                orders_by_id.setdefault(order_id, []).append(item)
                added_api_only += 1
                continue
            store_name = normalize_store_name(info.get("store_code"))
            if args.store and store_name != args.store:
                skipped_placeholder_store += 1
                continue
            kaspi_offer = _coerce_str(info.get("kaspi_offer_name"))
            kaspi_core = extract_name_core(kaspi_offer) if kaspi_offer else ""
            if not kaspi_core or kaspi_core.lower() == "unknown":
                kaspi_core = _coerce_str(info.get("sku_key")) or _coerce_str(info.get("sku_id")) or "UNKNOWN"
            quantity = int(info.get("quantity") or 1)
            item = OrderItem(
                order_id=order_id,
                store_name=store_name,
                kaspi_name_core=kaspi_core,
                my_size="",
                sku_key=_coerce_str(info.get("sku_key")),
                sku_id=_coerce_str(info.get("sku_id")),
                quantity=quantity,
                planned_date=info.get("planned_date"),
            )
            orders_by_id.setdefault(order_id, []).append(item)
            added_missing_crm_placeholders += 1

    if added_missing_crm_placeholders:
        print(
            f"  Added {added_missing_crm_placeholders} pending orders without size "
            f"({args.selection_source} selection missing row or size; allow-missing-size)"
        )
    if added_api_only:
        print(f"  Added {added_api_only} API-only pending orders (no CRM/DB)")
    if skipped_missing_current_crm:
        print(
            f"  Skipped {skipped_missing_current_crm} pending orders "
            f"(missing {args.selection_source} selection row or unresolved size)"
        )
    if skipped_placeholder_store:
        print(f"  Skipped {skipped_placeholder_store} pending orders (store filter)")

    if not orders_by_id and not missing_in_selection:
        print("No eligible orders in DB/API selection.")
        return 0
    if args.allow_missing_size:
        print(f"  Found {len(orders_by_id)} orders (size optional)")
    elif args.selection_source == "db":
        print(f"  Found {len(orders_by_id)} orders with assigned/manual size in DB")
    else:
        print(f"  Found {len(orders_by_id)} orders with MY_SIZE in CRM")

    # Quick per-store sanity: pending vs sized
    sized_by_store = defaultdict(int)
    for oid, items in orders_by_id.items():
        if not items:
            continue
        api_store = STORE_NAME_TO_API_CODE.get(items[0].store_name, items[0].store_name)
        sized_by_store[api_store] += 1
    for store_code, ids in pending_orders.items():
        sized = sized_by_store.get(store_code, 0)
        if sized < len(ids):
            print(f"  WARNING: {store_code} pending={len(ids)} sized={sized} (missing sizes?)")

    # Step 3: Ship orders
    print("\nStep 3: Shipping orders...")
    result = ship_orders(
        orders_by_id,
        pending_orders,
        order_id_to_base64,
        dry_run=args.dry_run,
        verbose=args.verbose,
        since_days=args.since_days,
    )

    # Summary
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Shipped: {result['shipped']}")
    print(f"  Skipped: {result['skipped']}")
    if result['errors']:
        print(f"  Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"    - {err}")
        if len(result['errors']) > 5:
            print(f"    ... and {len(result['errors']) - 5} more")

    if args.dry_run:
        print("\n  [DRY RUN] No API calls were made.")
        remaining_backlog = None
    else:
        remaining_pending, _remaining_base64, _remaining_planned, remaining_meta = get_pending_assembly_orders(
            target_date=target_date,
            since_days=args.since_days,
            store_codes=selected_store_codes,
            include_overdue=include_overdue,
            overdue_lookback_days=overdue_lookback_days,
        )
        remaining_backlog = build_pending_backlog_report(
            remaining_meta,
            target_date=target_date,
        )
        remaining_total = sum(len(ids) for ids in remaining_pending.values())
        result["remaining_pending"] = remaining_total
        result["remaining_overdue_pending"] = int(remaining_backlog["summary"].get("overdue_pending", 0))
        result["remaining_stale_pending"] = int(remaining_backlog["summary"].get("stale_pending", 0))
        result["remaining_backlog"] = remaining_backlog
        print_pending_backlog("  Remaining backlog after shipping...", remaining_backlog["summary"])

    report_json, report_md = write_pending_backlog_report(
        target_date=target_date,
        store_scope=args.store or "ALL_STORES",
        dry_run=bool(args.dry_run),
        include_overdue=include_overdue,
        overdue_lookback_days=overdue_lookback_days,
        initial_report=initial_backlog,
        remaining_report=remaining_backlog,
    )
    result["backlog_report_json"] = str(report_json)
    result["backlog_report_md"] = str(report_md)
    print(f"  Backlog report (md): {report_md}")
    print(f"  Backlog report (json): {report_json}")

    health = classify_ship_health(result)
    print(f"  Health: {health.code} ({health.message})")
    result["selection_source"] = args.selection_source
    result["target_date"] = target_date.isoformat()
    result["store_scope"] = args.store or "ALL_STORES"
    result["health_code"] = health.code
    result["health_message"] = health.message
    result["health_exit_code"] = health.exit_code
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    return health.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
