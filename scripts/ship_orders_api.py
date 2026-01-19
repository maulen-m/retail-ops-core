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
from core.paths import data_path, get_data_root
from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    APIResponse,
    KaspiAuthError,
    KaspiNotFoundError,
    KaspiWriteDisabledError,
    STORE_TOKEN_MAP,
)
from core.waybill.pdf_grouper import _extract_name_core as extract_name_core
from core.utils.kaspi_dates import planned_date_from_order

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
}

# Reverse mapping: display name -> store code for API
STORE_NAME_TO_API_CODE = {
    'AcmeWear': 'ACMEWEAR',
    'Universal': 'UNIVERSAL',
    '11KZ': '11KZ',
    'STORE-B': 'STOREB',
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
ASSEMBLE_VERIFY_RETRIES_UNIVERSAL = int(
    os.environ.get("KASPI_ASSEMBLE_VERIFY_RETRIES_UNIVERSAL", "1")
)
ASSEMBLE_VERIFY_DELAY_UNIVERSAL = float(
    os.environ.get("KASPI_ASSEMBLE_VERIFY_DELAY_UNIVERSAL", "0")
)
ASSEMBLE_REFRESH_RETRIES_UNIVERSAL = int(
    os.environ.get("KASPI_ASSEMBLE_REFRESH_RETRIES_UNIVERSAL", "2")
)
ASSEMBLE_REFRESH_DELAY_UNIVERSAL = float(
    os.environ.get("KASPI_ASSEMBLE_REFRESH_DELAY_UNIVERSAL", "60")
)


def _assemble_settings_for_store(store_code: str) -> tuple[int, float, int, float]:
    if store_code.upper() == "UNIVERSAL":
        return (
            ASSEMBLE_VERIFY_RETRIES_UNIVERSAL,
            ASSEMBLE_VERIFY_DELAY_UNIVERSAL,
            ASSEMBLE_REFRESH_RETRIES_UNIVERSAL,
            ASSEMBLE_REFRESH_DELAY_UNIVERSAL,
        )
    return (
        ASSEMBLE_VERIFY_RETRIES,
        ASSEMBLE_VERIFY_DELAY,
        ASSEMBLE_REFRESH_RETRIES,
        ASSEMBLE_REFRESH_DELAY,
    )


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


def _planned_date_from_order(order: dict) -> Optional[date]:
    """Extract planned courier transmission date from API order."""
    return planned_date_from_order(order)


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
    allow_missing_size: bool = False,
) -> dict[str, list[OrderItem]]:
    """
    Read orders from CRM Excel file, grouped by order_id.

    Filters for orders where:
    - MY_SIZE is filled
    - planned_date <= target_date
    - Optionally filtered by store

    Returns dict: order_id -> list[OrderItem]
    """
    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    logger.info(f"Reading CRM from {crm_path}")
    df = pd.read_excel(crm_path, sheet_name=sheet_name)

    orders_by_id: dict[str, list[OrderItem]] = defaultdict(list)
    skipped_no_size = 0
    missing_size_allowed = 0
    skipped_date = 0
    skipped_store = 0
    skipped_not_pending = 0
    used_db_size = 0
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
        db_size = _coerce_str(db_info.get("size")) if db_info else ""

        # Check MY_SIZE (DB first, CRM fallback)
        my_size = str(row.get('MY_SIZE', '')).strip()
        if my_size.lower() in ('nan', 'none', ''):
            my_size = ""

        final_size = db_size or my_size
        if not final_size:
            if not allow_missing_size:
                skipped_no_size += 1
                continue
            missing_size_allowed += 1
            final_size = ""
        if db_size:
            used_db_size += 1
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
        if kaspi_name_core.lower() == 'nan':
            kaspi_name_core = ""

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
    logger.info(f"Used DB sizes: {used_db_size}")
    logger.info(f"Used CRM sizes: {used_crm_size}")
    if store_filter:
        logger.info(f"Skipped {skipped_store} rows from other stores")
    if target_order_ids is not None:
        logger.info(f"Skipped {skipped_not_pending} rows not in pending assembly list")

    return dict(orders_by_id)


def get_pending_assembly_orders(
    target_date: Optional[date] = None,
    since_days: int = 7,
) -> tuple[dict[str, set[str]], dict[str, dict[str, str]], dict[str, dict[str, date]]]:
    """
    Get orders in "Упаковка" stage from ALL stores via API.

    Returns:
        - pending_by_store: dict store_api_code -> set of order_ids pending assembly
        - order_id_to_base64: dict store_code -> {order_code: base64_id}
    """
    pending_by_store: dict[str, set[str]] = {}
    # Store-scoped base64 IDs prevent cross-store collisions on assemble.
    order_id_to_base64: dict[str, dict[str, str]] = {}
    planned_date_by_store: dict[str, dict[str, date]] = {}

    since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')

    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
            result = client.get_pending_assembly_orders(since=since)
            if result.success:
                orders = result.data.get('data', [])
                order_ids = set()
                for order in orders:
                    order_code = order.get('attributes', {}).get('code', '')
                    base64_id = order.get('id', '')
                    planned_date = _planned_date_from_order(order)
                    if target_date and planned_date != target_date:
                        continue
                    if order_code:
                        order_ids.add(order_code)
                        if base64_id:
                            order_id_to_base64.setdefault(store_code, {})[order_code] = base64_id
                        if planned_date:
                            planned_date_by_store.setdefault(store_code, {})[order_code] = planned_date
                pending_by_store[store_code] = order_ids
                logger.info(f"{store_code}: {len(order_ids)} orders pending assembly")
            else:
                logger.warning(f"{store_code}: Could not fetch pending orders: {result.error}")
                pending_by_store[store_code] = set()
        except KaspiAuthError as e:
            logger.warning(f"{store_code}: Auth error - {e}")
            pending_by_store[store_code] = set()

    return pending_by_store, order_id_to_base64, planned_date_by_store


def ship_orders(
    orders_by_id: dict[str, list[OrderItem]],
    pending_orders: dict[str, set[str]],
    order_id_to_base64: dict[str, dict[str, str]],
    planned_date_by_store: dict[str, dict[str, date]],
    dry_run: bool = False,
    verbose: bool = False,
    since_days: int = 7,
    target_date: Optional[date] = None,
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

    today = datetime.now(ALMATY_TZ).date()
    future_target = bool(target_date and target_date > today)
    allow_future_assemble = os.environ.get("KASPI_ALLOW_FUTURE_ASSEMBLE", "0") == "1"
    defer_future = future_target and not allow_future_assemble
    debug_assemble = os.environ.get("KASPI_ASSEMBLE_DEBUG", "0") == "1"
    diag_enabled = os.environ.get("KASPI_ASSEMBLE_DIAG", "0") == "1" or debug_assemble
    diag_dir = Path(get_data_root()) / "exports" / "diagnostics"
    if diag_enabled:
        diag_dir.mkdir(parents=True, exist_ok=True)

    def _json_safe(value: Any) -> Any:
        try:
            json.dumps(value)
            return value
        except Exception:
            return str(value)

    def _response_to_dict(response: Optional[APIResponse]) -> Optional[dict]:
        if response is None:
            return None
        headers = {}
        request_info = {}
        request_id = None
        raw = response.raw_response
        if raw is not None:
            headers = dict(raw.headers)
            if raw.request is not None:
                request_info = {
                    "method": raw.request.method,
                    "url": raw.request.url,
                }
            for key, value in headers.items():
                if key.lower() in (
                    "x-request-id",
                    "x-requestid",
                    "x-correlation-id",
                    "x-trace-id",
                    "x-amzn-trace-id",
                ):
                    request_id = value
                    break
        return {
            "success": response.success,
            "status_code": response.status_code,
            "error": response.error,
            "data": _json_safe(response.data),
            "headers": headers,
            "request": request_info,
            "request_id": request_id,
        }

    def _write_diag(diag: dict) -> None:
        if not diag_enabled:
            return
        try:
            order_code = str(diag.get("order_code", "UNKNOWN"))
            store_code = str(diag.get("store_code", "UNKNOWN"))
            ts = diag.get("timestamp") or datetime.now(ALMATY_TZ).isoformat()
            ts_safe = ts.replace(":", "").replace("+", "").replace("-", "").replace("T", "_")[:15]
            filename = f"assemble_noop_{store_code}_{order_code}_{ts_safe}.json"
            path = diag_dir / filename
            with path.open("w", encoding="utf-8") as handle:
                json.dump(diag, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning(f"Failed to write assemble diagnostic: {exc}")

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

        is_universal = api_store_code == "UNIVERSAL"
        noop_consecutive = 0
        noop_total = 0
        refresh_processed = 0
        manual_required: set[str] = set()
        breaker_tripped = False

        print(f"\n  Processing {store_name} ({len(store_orders)} orders)...")
        verify_retries, verify_delay, refresh_retries, refresh_delay = _assemble_settings_for_store(
            api_store_code
        )
        retry_queue: dict[str, int] = {}

        def _order_snapshot(order_code: str, base64_id: Optional[str]) -> dict:
            snapshot: dict[str, Any] = {"at": datetime.now(ALMATY_TZ).isoformat()}
            if not diag_enabled:
                return snapshot
            if base64_id:
                try:
                    detail = client.get_order_by_id(base64_id)
                    snapshot["by_id"] = _response_to_dict(detail)
                except Exception as exc:
                    snapshot["by_id_error"] = str(exc)
            try:
                detail = client.get_order(order_code)
                snapshot["by_code"] = _response_to_dict(detail)
            except Exception as exc:
                snapshot["by_code_error"] = str(exc)
            return snapshot

        def _diag_add_attempt(diag: Optional[dict], label: str, payload: Optional[dict], response: APIResponse) -> None:
            if not diag_enabled or not diag:
                return
            diag.setdefault("attempts", []).append(
                {
                    "label": label,
                    "payload": payload,
                    "response": _response_to_dict(response),
                    "at": datetime.now(ALMATY_TZ).isoformat(),
                }
            )

        for order_id, items in store_orders.items():
            # Calculate package count
            parcel_count = calculate_package_count(items)
            diag: Optional[dict] = None
            diag_base64: Optional[str] = None
            diag_result: dict[str, Any] = {"shipped": False, "error": None}
            diag_written = False
            if diag_enabled:
                planned_for_diag = planned_date_by_store.get(api_store_code, {}).get(order_id)
                diag = {
                    "timestamp": datetime.now(ALMATY_TZ).isoformat(),
                    "store": store_name,
                    "store_code": api_store_code,
                    "order_code": order_id,
                    "base64_id": None,
                    "parcel_count": parcel_count,
                    "planned_date": planned_for_diag.isoformat() if planned_for_diag else None,
                    "attempts": [],
                }

            if verbose:
                item_desc = ", ".join(f"{i.kaspi_name_core}x{i.quantity}" for i in items)
                heavy_mark = " [HEAVY]" if any(is_heavy_item(i) for i in items) else ""
                print(f"    {order_id}: {parcel_count} pkg ({item_desc}){heavy_mark}")

            if dry_run:
                shipped += 1
                diag_result["shipped"] = True
                if diag is not None:
                    diag["after"] = _order_snapshot(order_id, None)
                    diag["result"] = diag_result
                    _write_diag(diag)
                continue

            # Helper: verify assemble state (handles delayed state updates)
            def _extract_attrs(detail: Optional[APIResponse]) -> dict:
                if not detail or not detail.success:
                    return {}
                data = detail.data
                if isinstance(data, dict) and isinstance(data.get('data'), dict):
                    return data['data'].get('attributes', {}) or {}
                if isinstance(data, dict):
                    return data.get('attributes', {}) or {}
                return {}

            def _extract_order_obj(detail: Optional[APIResponse]) -> dict:
                if not detail or not detail.success:
                    return {}
                data = detail.data
                if isinstance(data, dict) and isinstance(data.get('data'), dict):
                    return data['data']
                if isinstance(data, dict):
                    return data
                return {}

            def _log_assemble_state(prefix: str, detail: Optional[APIResponse]) -> None:
                if not debug_assemble:
                    return
                if not detail or not detail.success:
                    err = detail.error if detail else "no response"
                    print(f"      -> {prefix} detail_error={err}")
                    return
                attrs = _extract_attrs(detail)
                status = attrs.get('status')
                assembled = attrs.get('assembled')
                state = attrs.get('state')
                waybill = bool(client.get_waybill_url(_extract_order_obj(detail)))
                print(
                    f"      -> {prefix} state={state} status={status} assembled={assembled} waybill={int(waybill)}"
                )

            def _finalize_diag() -> None:
                nonlocal diag_written
                if not diag_enabled or diag_written or diag is None:
                    return
                diag["after"] = _order_snapshot(order_id, diag_base64)
                diag["result"] = diag_result
                _write_diag(diag)
                diag_written = True

            def _wait_for_assembled(order_code: str, base64_hint: Optional[str] = None) -> bool:
                for attempt in range(verify_retries):
                    try:
                        detail = None
                        if base64_hint:
                            detail = client.get_order_by_id(base64_hint)
                            _log_assemble_state("by_id", detail)
                            attrs = _extract_attrs(detail)
                            status = str(attrs.get('status', '')).upper()
                            if (
                                attrs.get('assembled') is True
                                or status == 'ASSEMBLED'
                                or client.get_waybill_url(_extract_order_obj(detail))
                            ):
                                if verbose:
                                    print("      -> Already assembled, skipping")
                                return True
                        detail = client.get_order(order_code)
                        _log_assemble_state("by_code", detail)
                        attrs = _extract_attrs(detail)
                        status = str(attrs.get('status', '')).upper()
                        if (
                            attrs.get('assembled') is True
                            or status == 'ASSEMBLED'
                            or client.get_waybill_url(_extract_order_obj(detail))
                        ):
                            if verbose:
                                print("      -> Already assembled, skipping")
                            return True
                    except Exception:
                        pass
                    if attempt < verify_retries - 1:
                        time.sleep(verify_delay)
                return False

            def _queue_retry(order_code: str, parcels: int) -> None:
                retry_queue.setdefault(order_code, parcels)
                if verbose:
                    print("      -> Queued for retry (refresh pending list)")

            def _fallback_assemble(reason: str, base64_hint: Optional[str] = None) -> bool:
                if verbose:
                    print(f"      -> WARN: {reason}. Retrying with order code...")
                try:
                    result_fallback: Optional[APIResponse] = None
                    diag_payload = None
                    diag_label = "fallback"
                    if base64_hint:
                        result_fallback = client.assemble_order_by_id_fallback(
                            base64_hint,
                            order_id,
                            parcel_count=parcel_count,
                        )
                        diag_label = "fallback_by_id"
                        diag_payload = {"data": {"numberOfSpace": str(parcel_count)}}
                        err_text = str(result_fallback.error or "")
                        if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                            result_fallback = client.assemble_order(
                                order_id,
                                parcel_count=parcel_count,
                            )
                            diag_label = "fallback_by_code"
                            diag_payload = {
                                "data": {
                                    "attributes": {
                                        "status": "ASSEMBLE",
                                        "code": order_id,
                                        "numberOfSpace": str(parcel_count),
                                    }
                                }
                            }
                    else:
                        result_fallback = client.assemble_order(order_id, parcel_count=parcel_count)
                        diag_label = "fallback_by_code"
                        diag_payload = {
                            "data": {
                                "attributes": {
                                    "status": "ASSEMBLE",
                                    "code": order_id,
                                    "numberOfSpace": str(parcel_count),
                                }
                            }
                        }
                    _diag_add_attempt(diag, diag_label, diag_payload, result_fallback)
                    if debug_assemble and result_fallback:
                        print(
                            "      -> assemble fallback "
                            f"status={result_fallback.status_code} "
                            f"success={result_fallback.success} error={result_fallback.error}"
                        )
                    if result_fallback.success:
                        if defer_future:
                            if verbose:
                                print("      -> Deferred (future planned date)")
                            return False
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
            diag_base64 = base64_id
            if diag is not None and "before" not in diag:
                diag["base64_id"] = base64_id
                diag["before"] = _order_snapshot(order_id, base64_id)
            if not base64_id:
                # If missing, fallback to direct lookup by order code.
                if _fallback_assemble("No Base64 ID found (state changed?)"):
                    shipped += 1
                    diag_result["shipped"] = True
                    _finalize_diag()
                else:
                    diag_result["error"] = "No Base64 ID; fallback failed"
                    _finalize_diag()
                continue

            # Call API with pre-fetched Base64 ID (avoids re-fetch 404)
            try:
                primary_payload = {
                    "data": {
                        "type": "orders",
                        "id": base64_id,
                        "attributes": {
                            "status": "ASSEMBLE",
                            "code": order_id,
                            "numberOfSpace": str(parcel_count),
                        },
                    }
                }
                result = client.assemble_order_by_id(base64_id, order_id, parcel_count=parcel_count)
                _diag_add_attempt(diag, "primary", primary_payload, result)
                if debug_assemble:
                    print(
                        "      -> assemble primary "
                        f"status={result.status_code} success={result.success} error={result.error}"
                    )
                if result.success:
                    if _wait_for_assembled(order_id, base64_id):
                        shipped += 1
                        diag_result["shipped"] = True
                        if verbose:
                            print("      -> Shipped OK")
                        _finalize_diag()
                    else:
                        if _fallback_assemble("No state change after primary assemble", base64_id):
                            shipped += 1
                            diag_result["shipped"] = True
                        else:
                            diag_result["error"] = "No state change after primary assemble"
                        _finalize_diag()
                        continue
                else:
                    # Some API errors return 404-equivalent errors without raising.
                    err_text = str(result.error or "")
                    if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                        if _wait_for_assembled(order_id, base64_id):
                            shipped += 1
                            diag_result["shipped"] = True
                            _finalize_diag()
                            continue
                        _queue_retry(order_id, parcel_count)
                        diag_result["error"] = "Not found; queued for retry"
                        _finalize_diag()
                        continue
                    errors.append(f"{order_id}: API error - {result.error}")
                    diag_result["error"] = f"API error - {result.error}"
                    if verbose:
                        print(f"      -> ERROR: {result.error}")
            except KaspiNotFoundError as e:
                # Retry with direct lookup if base64 ID is stale or mismatched.
                if _fallback_assemble(str(e), base64_id):
                    shipped += 1
                    diag_result["shipped"] = True
                    _finalize_diag()
            except KaspiWriteDisabledError:
                logger.error("Write operations disabled. Set ENABLE_KASPI_WRITE=1 in .env")
                diag_result["error"] = "Write operations disabled"
                _finalize_diag()
                return {
                    'shipped': 0,
                    'skipped': len(orders_by_id),
                    'errors': ['Write operations disabled'],
                }
            except Exception as e:
                # Unknown exception: try fallback once, then record error.
                if _fallback_assemble(str(e), base64_id):
                    shipped += 1
                    diag_result["shipped"] = True
                    _finalize_diag()
                else:
                    errors.append(f"{order_id}: {str(e)}")
                    diag_result["error"] = str(e)
                    if verbose:
                        print(f"      -> EXCEPTION: {e}")
            _finalize_diag()

        if retry_queue and refresh_retries > 0:
            refresh_since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')
            if verbose:
                print(f"  Retrying {len(retry_queue)} orders after refresh...")
            for attempt in range(refresh_retries):
                if refresh_delay > 0:
                    time.sleep(refresh_delay)
                refreshed = client.get_pending_assembly_orders(since=refresh_since)
                if not refreshed.success:
                    errors.append(f"{store_name}: refresh pending failed - {refreshed.error}")
                    break
                refreshed_map: dict[str, str] = {}
                refreshed_planned: dict[str, int] = {}
                for order in refreshed.data.get('data', []):
                    order_code = order.get('attributes', {}).get('code', '')
                    if not order_code:
                        continue
                    base64_id = order.get('id', '')
                    if base64_id:
                        refreshed_map[order_code] = base64_id
                    planned_date = _planned_date_from_order(order)
                    if planned_date:
                        refreshed_planned[order_code] = planned_date
                still_retry: dict[str, int] = {}
                retry_items = list(retry_queue.items())
                for idx, (order_code, parcels) in enumerate(retry_items):
                    base64_id = refreshed_map.get(order_code)
                    if not base64_id:
                        if _wait_for_assembled(order_code):
                            shipped += 1
                            continue
                        if verbose:
                            print(f"      {order_code}: Still pending/unknown after refresh")
                        still_retry[order_code] = parcels
                        continue
                    planned_date = refreshed_planned.get(order_code)
                    result = client.assemble_order_by_id(base64_id, order_code, parcel_count=parcels)
                    if debug_assemble:
                        print(
                            f"      {order_code}: assemble refresh "
                            f"status={result.status_code} success={result.success} error={result.error}"
                        )
                    refresh_processed += 1
                    assembled = False
                    http_success = False
                    if result.success:
                        http_success = True
                        if _wait_for_assembled(order_code, base64_id):
                            shipped += 1
                            noop_consecutive = 0
                            assembled = True
                            if verbose:
                                print(f"      {order_code}: Shipped OK (refresh)")
                            continue
                        fallback = client.assemble_order_by_id_fallback(
                            base64_id,
                            order_code,
                            parcel_count=parcels,
                        )
                        if debug_assemble:
                            print(
                                f"      {order_code}: fallback refresh "
                                f"status={fallback.status_code} success={fallback.success} "
                                f"error={fallback.error}"
                            )
                        if fallback.success and _wait_for_assembled(order_code, base64_id):
                            shipped += 1
                            noop_consecutive = 0
                            assembled = True
                            if verbose:
                                print(f"      {order_code}: Shipped OK (refresh fallback)")
                            continue
                        err_text = str(fallback.error or "")
                        if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                            if _wait_for_assembled(order_code, base64_id):
                                shipped += 1
                                noop_consecutive = 0
                                assembled = True
                                continue
                        if http_success and not assembled:
                            noop_total += 1
                            noop_consecutive += 1
                        still_retry[order_code] = parcels
                        if is_universal:
                            noop_rate = noop_total / refresh_processed if refresh_processed else 0
                            if noop_consecutive >= 5 or (refresh_processed >= 10 and noop_rate > 0.8):
                                breaker_tripped = True
                                manual_required.update(still_retry.keys())
                                manual_required.update(code for code, _ in retry_items[idx:])
                                break
                        continue
                    err_text = str(result.error or "")
                    if "not found" in err_text.lower() or "resource not found" in err_text.lower():
                        if _wait_for_assembled(order_code, base64_id):
                            shipped += 1
                            noop_consecutive = 0
                            continue
                        still_retry[order_code] = parcels
                        noop_consecutive = 0
                        if is_universal:
                            noop_rate = noop_total / refresh_processed if refresh_processed else 0
                            if noop_consecutive >= 5 or (refresh_processed >= 10 and noop_rate > 0.8):
                                breaker_tripped = True
                                manual_required.update(still_retry.keys())
                                manual_required.update(code for code, _ in retry_items[idx:])
                                break
                        continue
                    errors.append(f"{order_code}: API error - {result.error} (refresh)")
                    if verbose:
                        print(f"      {order_code}: ERROR - {result.error} (refresh)")
                    noop_consecutive = 0
                    if is_universal:
                        noop_rate = noop_total / refresh_processed if refresh_processed else 0
                        if noop_consecutive >= 5 or (refresh_processed >= 10 and noop_rate > 0.8):
                            breaker_tripped = True
                            manual_required.update(still_retry.keys())
                            manual_required.update(code for code, _ in retry_items[idx:])
                            break
                if breaker_tripped:
                    retry_queue = {}
                    break
                retry_queue = still_retry
                if not retry_queue:
                    break
            if retry_queue:
                for order_code in retry_queue:
                    planned_date = planned_date_by_store.get(api_store_code, {}).get(order_code)
                    if planned_date:
                        errors.append(
                            f"{order_code}: Not assembled after refresh (planned {planned_date.isoformat()})"
                        )
                    else:
                        errors.append(f"{order_code}: Not assembled after refresh")
        if breaker_tripped and manual_required:
            diag_dir.mkdir(parents=True, exist_ok=True)
            date_label = (target_date or today).strftime("%Y-%m-%d")
            manual_path = diag_dir / f"universal_manual_assemble_required_{date_label}.csv"
            try:
                with manual_path.open("w", encoding="utf-8") as handle:
                    handle.write("order_code\n")
                    for code in sorted(manual_required):
                        handle.write(f"{code}\n")
            except Exception as exc:
                logger.error(f"Failed to write manual assemble list: {exc}")
            logger.error(
                "!!! UNIVERSAL assemble circuit breaker triggered "
                f"(no-op consecutive={noop_consecutive}, no-op total={noop_total}/{refresh_processed})."
            )
            logger.error(
                f"Manual step required: assemble UNIVERSAL orders in Kaspi Seller UI, "
                f"then rerun run_build_waybills.command --skip-ship. "
                f"List: {manual_path}"
            )
            errors.append(
                "UNIVERSAL: assemble circuit breaker triggered; manual assemble required"
            )

    return {
        'shipped': shipped,
        'skipped': skipped,
        'errors': errors,
    }


def main():
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
        '--since-days',
        type=int,
        default=7,
        help='Days to look back in API (default: 7)'
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
        '--merchant-uid',
        help='Override X-Merchant-Uid header value for Kaspi API (optional)'
    )
    parser.add_argument(
        '--use-merchant-uid',
        action='store_true',
        help='Enable X-Merchant-Uid header using config/env values'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    if args.merchant_uid:
        os.environ["KASPI_MERCHANT_UID_OVERRIDE"] = args.merchant_uid
        os.environ["KASPI_SEND_MERCHANT_UID"] = "1"
    elif args.use_merchant_uid:
        os.environ["KASPI_SEND_MERCHANT_UID"] = "1"

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(ALMATY_TZ).date()
    today = datetime.now(ALMATY_TZ).date()
    allow_future_assemble = os.environ.get("KASPI_ALLOW_FUTURE_ASSEMBLE", "0") == "1"
    if target_date > today and not allow_future_assemble:
        print("=" * 60)
        print("  Kaspi Order Shipping (Set Package Count)")
        print("=" * 60)
        print(f"  Data root: {get_data_root()}")
        print(f"  CRM file: {args.crm_file}")
        print(f"  Target date: {target_date}")
        print("  NOTE: Target date is in the future. Assembly is skipped by default.")
        print("        Set KASPI_ALLOW_FUTURE_ASSEMBLE=1 to override.")
        print()
        return

    print("=" * 60)
    print("  Kaspi Order Shipping (Set Package Count)")
    print("=" * 60)
    print(f"  Data root: {get_data_root()}")
    print(f"  CRM file: {args.crm_file}")
    print(f"  Target date: {target_date}")
    if args.store:
        print(f"  Store filter: {args.store}")
    if args.dry_run:
        print("  [DRY RUN MODE - No API calls]")
    print()

    # Step 1: Get pending assembly orders from API
    print("Step 1: Fetching pending assembly orders from API...")
    pending_orders, order_id_to_base64, planned_date_by_store = get_pending_assembly_orders(
        target_date=target_date,
        since_days=args.since_days,
    )

    total_pending = sum(len(ids) for ids in pending_orders.values())
    if total_pending == 0:
        print("No orders pending assembly in Kaspi (Упаковка stage).")
        return

    print(f"  Found {total_pending} orders pending assembly across all stores")

    all_pending = set()
    for order_ids in pending_orders.values():
        all_pending.update(order_ids)
    pending_store_for_order: dict[str, str] = {}
    for store_code, order_ids in pending_orders.items():
        for order_id in order_ids:
            pending_store_for_order[order_id] = store_code

    # Step 2: Read orders from CRM
    print("\nStep 2: Reading CRM for MY_SIZE data (DB-first)...")
    resolved_db_path = resolve_db_path(None)
    if resolved_db_path:
        print(f"  DB: {resolved_db_path}")
    db_order_info = load_db_order_info(resolved_db_path or DEFAULT_DB_PATH, all_pending)
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

    # Add DB-only orders missing in CRM (still pending in Kaspi)
    missing_in_crm = all_pending - set(orders_by_id.keys())
    added_db_only = 0
    skipped_db_no_size = 0
    skipped_db_store = 0
    missing_db_size_allowed = 0
    added_api_only = 0
    if missing_in_crm:
        for order_id in missing_in_crm:
            info = db_order_info.get(order_id)
            if not info:
                if not args.allow_missing_size:
                    continue
                store_code = pending_store_for_order.get(order_id)
                if args.store:
                    expected_code = STORE_NAME_TO_API_CODE.get(args.store, args.store)
                    if store_code and store_code != expected_code:
                        skipped_db_store += 1
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
            size = _coerce_str(info.get("size"))
            if not size:
                if not args.allow_missing_size:
                    skipped_db_no_size += 1
                    continue
                missing_db_size_allowed += 1
                size = ""
            store_name = normalize_store_name(info.get("store_code"))
            if args.store and store_name != args.store:
                skipped_db_store += 1
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
                my_size=size,
                sku_key=_coerce_str(info.get("sku_key")),
                sku_id=_coerce_str(info.get("sku_id")),
                quantity=quantity,
                planned_date=info.get("planned_date"),
            )
            orders_by_id.setdefault(order_id, []).append(item)
            added_db_only += 1

    if added_db_only:
        print(f"  Added {added_db_only} DB-only pending orders (CRM missing)")
    if added_api_only:
        print(f"  Added {added_api_only} API-only pending orders (no CRM/DB)")
    if skipped_db_no_size:
        print(f"  Skipped {skipped_db_no_size} pending orders (no size in DB/CRM)")
    if skipped_db_store:
        print(f"  Skipped {skipped_db_store} pending orders (store filter)")
    if missing_db_size_allowed:
        print(f"  Included {missing_db_size_allowed} pending orders without size (allow-missing-size)")

    if not orders_by_id and not missing_in_crm:
        print("No eligible orders in CRM/DB.")
        return
    if args.allow_missing_size:
        print(f"  Found {len(orders_by_id)} orders (size optional)")
    else:
        print(f"  Found {len(orders_by_id)} orders with MY_SIZE (CRM+DB)")

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
        planned_date_by_store,
        dry_run=args.dry_run,
        verbose=args.verbose,
        since_days=args.since_days,
        target_date=target_date,
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


if __name__ == "__main__":
    main()
