#!/usr/bin/env python3
"""
Build daily waybill bundles from CRM and waybill ZIPs.

Phase 11 TASK-192: Daily waybill grouping workflow.

Reads orders from SALES_KSP_CRM_V3.xlsx (with MY_SIZE filled), extracts waybill PDFs
from ZIP files, groups them by store/type, and creates organized output folders with manifests.

If --include-overdue is used, outputs are split into TODAY/OVERDUE subfolders.
For dual-layout output, a dedicated MERGED/SEND root is also produced so the
WhatsApp sender can use one fully merged source across stores and partitions.

Usage:
    python scripts/build_daily_waybills.py
    python scripts/build_daily_waybills.py --date 2025-12-10
    python scripts/build_daily_waybills.py --lookback-days 14
    python scripts/build_daily_waybills.py --dry-run --verbose
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import chain
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Optional

# Re-exec with venv python if available (ensures dependencies)
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if __name__ == "__main__" and os.environ.get("VIRTUAL_ENV") is None and VENV_PYTHON.exists():
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

import pandas as pd
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Kaspi dates are in Asia/Almaty timezone
ALMATY_TZ = ZoneInfo("Asia/Almaty")
READY_STATUS_RU = "Ожидает передачи курьеру"
READY_STATUS_EN = "Awaiting courier"
ACCEPTED_STATUS_RU = "Принят"
ACCEPTED_STATUS_EN = "Accepted"

# Project root
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from core.db import DEFAULT_DB_PATH, get_db
from core.ops.crm_operational_view import (
    select_operational_crm_rows,
    select_operational_crm_rows_with_targeted_fallback,
)
from core.ops.waybill_send_batch import SEND_LEDGER_FILE, initialize_send_ledger
from core.ops.waybill_overdue_carryforward import (
    get_overdue_waybill_ready_order_ids_from_db,
)
from core.paths import data_path, get_data_root
from core.utils.kaspi_dates import parse_kaspi_date
from core.waybill.pdf_grouper import _extract_name_core as extract_name_core
from core.waybill.pdf_grouper import merge_pdfs
from core.integrations.kaspi_api_client import KaspiAPIClient, STORE_TOKEN_MAP, KaspiAuthError
from core.stores.roster import load_sync_enabled_kaspi_store_codes
from core.integrations.kaspi_order_stage import (
    StageCode,
    api_state_filter_for_stage,
    classify_kaspi_order_stage,
    classify_kaspi_stage_from_db_row,
)
from core.utils.kaspi_dates import planned_date_from_order
from core.utils.kaspi_name_core_resolver import (
    SAFE_KASPI_NAME_CORE_SOURCES,
    KaspiNameCoreMaps,
    load_active_kaspi_name_core_maps,
    resolve_kaspi_name_core,
)
from core.utils.kaspi_order_core_overrides import load_order_name_core_overrides

# Default paths
DEFAULT_CRM_PATH = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_WAYBILL_DIR = data_path("excel_ui", "ActiveOrders")
DEFAULT_OUTPUT_DIR = data_path("excel_ui", "Kaspi_orders", "Today")
DEFAULT_SHEET_NAME = "SALES_KSP_CRM_1"
OUTPUT_LAYOUT_LEGACY = "legacy"
OUTPUT_LAYOUT_PER_STORE_AND_MERGED = "per-store-and-merged"
WHATSAPP_SEND_ROOT_NAME = "SEND"

# Store code mapping (Kaspi warehouse codes -> display names)
STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
}


def _is_signature_required(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "да", "требуется", "required"}:
        return True
    if text in {"false", "0", "no", "нет", "не требуется", "not required"}:
        return False
    return False


def _is_ready_status(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.upper() in {"READY", "NEW"}:
        return True
    return text in {
        READY_STATUS_RU,
        READY_STATUS_EN,
        ACCEPTED_STATUS_RU,
        ACCEPTED_STATUS_EN,
    }


def _is_pending_handover_stage(order: dict) -> bool:
    stage = classify_kaspi_order_stage(order)
    return stage in {
        StageCode.ACCEPTED_PENDING_ASSEMBLY,
        StageCode.ASSEMBLED_PENDING_HANDOVER,
    }


def _is_legacy_db_ready_for_waybill(row: Any) -> bool:
    if not hasattr(row, "get"):
        row = dict(row)
    state = _coerce_str(row.get("kaspi_status") or row.get("state")).upper()
    detail = _coerce_str(row.get("kaspi_status_detail") or row.get("status"))
    legacy_handover_state = str(api_state_filter_for_stage(StageCode.ASSEMBLED_PENDING_HANDOVER) or "").upper()
    if state != legacy_handover_state or detail:
        return False
    if _is_signature_required(row.get("signature_required") or row.get("signatureRequired")):
        return False
    if row.get("courier_transmission_date") or row.get("actual_shipment_date"):
        return False
    return _is_ready_status(row.get("internal_status") or row.get("status_internal"))

# Reverse mapping for lookup
STORE_NAME_TO_CODE = {v: k for k, v in STORE_MAP.items()}

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
}

# Size sort order
SIZE_ORDER = {
    # Kids numeric sizes
    '22': 1, '24': 2, '26': 3, '28': 4, '30': 5,
    # Men's letter sizes
    'S': 10, 'M': 11, 'L': 12, 'XL': 13, '2XL': 14, '3XL': 15, '4XL': 16,
}
ORDERING_COLOR_TOKENS = {
    "BLACK", "WHITE", "GRAY", "GREY", "RED", "BLUE", "GREEN", "BROWN", "BEIGE",
    "PINK", "PURPLE", "YELLOW", "ORANGE",
    "ЧЕРНЫЙ", "ЧЕРНАЯ", "ЧЕРНОЕ", "ЧЕРНЫЕ",
    "БЕЛЫЙ", "БЕЛАЯ", "БЕЛОЕ", "БЕЛЫЕ",
    "СЕРЫЙ", "СЕРАЯ", "СЕРОЕ", "СЕРЫЕ",
    "КРАСНЫЙ", "КРАСНАЯ", "КРАСНОЕ", "КРАСНЫЕ",
    "СИНИЙ", "СИНЯЯ", "СИНЕЕ", "СИНИЕ",
    "ЗЕЛЕНЫЙ", "ЗЕЛЕНАЯ", "ЗЕЛЕНОЕ", "ЗЕЛЕНЫЕ",
    "КОРИЧНЕВЫЙ", "КОРИЧНЕВАЯ", "КОРИЧНЕВОЕ", "КОРИЧНЕВЫЕ",
    "БЕЖЕВЫЙ", "БЕЖЕВАЯ", "БЕЖЕВОЕ", "БЕЖЕВЫЕ",
    "РОЗОВЫЙ", "РОЗОВАЯ", "РОЗОВОЕ", "РОЗОВЫЕ",
    "ФИОЛЕТОВЫЙ", "ФИОЛЕТОВАЯ", "ФИОЛЕТОВОЕ", "ФИОЛЕТОВЫЕ",
    "ЖЕЛТЫЙ", "ЖЕЛТАЯ", "ЖЕЛТОЕ", "ЖЕЛТЫЕ",
    "ОРАНЖЕВЫЙ", "ОРАНЖЕВАЯ", "ОРАНЖЕВОЕ", "ОРАНЖЕВЫЕ",
}
ORDERING_NOISE_TOKENS = {
    "CL", "NEW", "CLO", "MEN", "MAN", "WOMEN", "WOMAN", "KID", "KIDS",
    "PROD", "SKU", "COLOR", "SIZE", "PP1",
}
SEND_CATEGORY_PRIORITY = {
    "SPECIAL_multi_line": 0,
    "SPECIAL_multi_qty": 1,
    "NORMAL_singles": 2,
}
SEND_PRIORITY_FAMILY_ALIASES = {
    "LINE51",
    "BLE51",
    "6В1_+СУМКА",
    "LINE61",
    "SUT61",
}

# Waybill PDF pattern
WAYBILL_PATTERN = r'KASPI_SHOP-(\d+)\.pdf'


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
    kaspi_offer_name: str
    planned_date: Optional[date]
    source_row_id: str = ""
    kaspi_name_core_source: str = ""


@dataclass
class WaybillGroup:
    """Group of items for waybill processing."""
    group_type: str  # NORMAL, MULTI_LINE, MULTI_QTY
    store_name: str
    items: list[OrderItem] = field(default_factory=list)
    pdf_path: Optional[Path] = None
    pdf_paths: list[Path] = field(default_factory=list)
    output_filename: str = ""

    @property
    def order_id(self) -> str:
        return self.items[0].order_id if self.items else ""

    @property
    def order_ids(self) -> list[str]:
        ids = [item.order_id for item in self.items if item.order_id]
        return sorted(set(ids))

    @property
    def kaspi_name_core(self) -> str:
        return self.items[0].kaspi_name_core if self.items else ""

    @property
    def my_size(self) -> str:
        return self.items[0].my_size if self.items else ""

    @property
    def sku_key(self) -> str:
        return self.items[0].sku_key if self.items else ""

    @property
    def sku_id(self) -> str:
        return self.items[0].sku_id if self.items else ""

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items)


def sanitize_filename(name: str) -> str:
    """
    Sanitize filename for filesystem safety.

    Removes/replaces problematic characters but preserves Cyrillic.
    """
    if not name:
        return "UNKNOWN"

    # Replace problematic characters
    result = re.sub(r'[/\\:*?"<>|\s,;]', '_', str(name))

    # Remove multiple consecutive underscores
    result = re.sub(r'_+', '_', result)

    # Remove leading/trailing underscores
    result = result.strip('_')

    # Truncate very long names
    if len(result) > 80:
        result = result[:80]

    return result if result else "UNKNOWN"


def format_item_detail(item: OrderItem) -> str:
    """Compact warehouse-readable item detail with explicit quantity."""
    core = sanitize_filename(item.kaspi_name_core)
    size = sanitize_filename(item.my_size)
    qty = int(item.quantity or 0)
    if qty <= 0:
        qty = 1
    return f"{core}-{size}-{qty}"


def parse_date(value: Any) -> Optional[date]:
    """Parse mixed CRM/DB date values without flipping ISO month/day order."""
    return parse_kaspi_date(value)


def normalize_store_name(value: Any) -> str:
    """Normalize store name from various formats."""
    if pd.isna(value) or not value:
        return "UNKNOWN"

    store_str = str(value).strip()

    # Direct match
    if store_str in STORE_MAP:
        return STORE_MAP[store_str]

    # Already a display name
    if store_str in STORE_NAME_TO_CODE:
        return store_str

    # Case-insensitive lookup
    for code, name in STORE_MAP.items():
        if code.lower() == store_str.lower() or name.lower() == store_str.lower():
            return name

    return store_str


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


def _planned_date_from_order(order: dict, store_code: Optional[str] = None) -> Optional[date]:
    """Extract planned courier transmission date from API order."""
    return planned_date_from_order(order, store_code=store_code)


def get_api_order_ids_for_date(
    target_date: date,
    since_days: int = 7,
    store_filter: Optional[str] = None,
    verbose: bool = False,
    include_overdue: bool = False,
) -> tuple[dict[str, set[str]], set[str]]:
    """Fetch pending-handover orders from API and return order IDs for target_date."""
    orders_by_store: dict[str, set[str]] = {}
    error_stores: set[str] = set()

    stores = [store for store in load_sync_enabled_kaspi_store_codes() if store in STORE_TOKEN_MAP]
    if store_filter:
        store_filter = store_filter.upper()
        if store_filter in STORE_TOKEN_MAP:
            stores = [store_filter]

    since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')

    min_date = target_date - timedelta(days=since_days)
    for store_code in stores:
        try:
            client = KaspiAPIClient(store_code=store_code)
            orders = client.list_all_orders(
                state=api_state_filter_for_stage(StageCode.ACCEPTED_PENDING_ASSEMBLY),
                since=since,
                include_orders='user',
            )
        except KaspiAuthError as exc:
            logger.warning(f"{store_code}: Auth error - {exc}")
            error_stores.add(store_code)
            continue
        except Exception as exc:
            logger.warning(f"{store_code}: API error - {exc}")
            error_stores.add(store_code)
            continue

        if verbose:
            logger.info(f"{store_code}: API returned {len(orders)} orders")

        ids: set[str] = set()
        for order in orders:
            attrs = order.get("attributes", {}) or {}
            if not _is_pending_handover_stage(order):
                continue
            planned_date = _planned_date_from_order(order, store_code=store_code)
            if include_overdue:
                if planned_date and min_date <= planned_date <= target_date:
                    order_code = order.get('attributes', {}).get('code', '')
                    if order_code:
                        ids.add(order_code)
            else:
                if planned_date == target_date:
                    order_code = order.get('attributes', {}).get('code', '')
                    if order_code:
                        ids.add(order_code)

        if ids:
            orders_by_store[store_code] = ids
        if verbose:
            logger.info(f"{store_code}: {len(ids)} orders for {target_date}")

    return orders_by_store, error_stores


def _selection_mode(include_overdue: bool, exact_date: bool) -> str:
    if include_overdue:
        return "overdue"
    if exact_date:
        return "exact"
    return "exact"


def load_selection_cache(
    waybill_dir: Path,
    target_date: date,
    include_overdue: bool,
    exact_date: bool,
) -> Optional[dict[str, set[str]]]:
    """Load API selection cache from waybill download step, if compatible."""
    cache_path = waybill_dir / "waybills" / "_waybill_selection_orders.json"
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if payload.get("target_date") != target_date.isoformat():
        return None

    requested_mode = _selection_mode(include_overdue, exact_date)
    cache_mode = "overdue" if payload.get("include_overdue") else "exact"
    if payload.get("all_dates"):
        cache_mode = "all"
    if requested_mode != cache_mode:
        return None

    stores = {store: set(order_ids or []) for store, order_ids in (payload.get("stores") or {}).items()}
    if not any(stores.values()):
        return None
    return stores


def normalize_store_display(value: Any) -> str:
    """Normalize DB store_code to display store name."""
    if pd.isna(value) or not value:
        return "UNKNOWN"
    raw = str(value).strip()
    if not raw:
        return "UNKNOWN"
    upper = raw.upper()
    db_map = {
        "UNIVERSAL": "Universal",
        "ACMEWEAR": "AcmeWear",
        "PP1": "AcmeWear",
        "PP2": "AcmeWear",
        "11KZ": "11KZ",
        "STOREB": "STORE-B",
        "STORE-B": "STORE-B",
        "MELVIS": "Store-C",
    }
    if upper in db_map:
        return db_map[upper]
    return normalize_store_name(raw)


def _coerce_str(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def load_crm_dataframe(crm_path: Path, sheet_name: str) -> Optional[pd.DataFrame]:
    """Load CRM once to avoid repeated reads."""
    if not crm_path.exists():
        return None
    try:
        logger.info(f"Reading CRM from {crm_path}")
        return pd.read_excel(crm_path, sheet_name=sheet_name)
    except Exception as exc:
        logger.warning(f"Failed to read CRM workbook: {exc}")
        return None


def _pick_size(assigned_size: Any, my_size: Any) -> str:
    """Prefer assigned_size from DB, fallback to my_size."""
    size = _coerce_str(assigned_size)
    if size and size.lower() not in ("nan", "none"):
        return size
    size = _coerce_str(my_size)
    if size and size.lower() not in ("nan", "none"):
        return size
    return ""


def _is_blankish_db_source_value(value: Any) -> bool:
    text = _coerce_str(value)
    return not text or text.lower() in {"nan", "none", "null"}


def _db_shadow_group_key(row: Any) -> tuple[str, str, str]:
    order_id = _coerce_str(row["order_id"])
    if order_id.endswith(".0"):
        order_id = order_id[:-2]
    store_code = _coerce_str(row["store_code"]).upper()
    if store_code == "STORE-B":
        store_code = "STOREB"
    return (order_id, store_code, _coerce_str(row["planned_shipment_date"]))


def _is_placeholder_db_shadow_row(row: Any) -> bool:
    return (
        _is_blankish_db_source_value(row["kaspi_offer_name"])
        and _is_blankish_db_source_value(row["sku_key"])
        and _is_blankish_db_source_value(row["sku_id"])
    )


def _drop_placeholder_db_shadow_rows(rows: list[Any]) -> list[Any]:
    """Remove blank duplicate rows that would create phantom UNKNOWN multi-line bundles."""
    concrete_groups = {
        _db_shadow_group_key(row)
        for row in rows
        if not _is_placeholder_db_shadow_row(row)
    }
    if not concrete_groups:
        return rows
    return [
        row
        for row in rows
        if not (_is_placeholder_db_shadow_row(row) and _db_shadow_group_key(row) in concrete_groups)
    ]


def read_db_orders(
    db_path: Path,
    target_date: date,
    lookback_days: Optional[int] = None,
    order_id_filter: Optional[set[str]] = None,
) -> list[OrderItem]:
    """
    Read orders from fact_orders_kaspi (DB-first).

    Filters for orders where:
    - assigned_size OR my_size is present
    - planned_shipment_date within [target_date - lookback_days, target_date]
      OR order_id_filter is provided (API-based selection)
    """
    if not db_path or not db_path.exists():
        logger.warning(f"DB not found: {db_path}")
        return []

    with get_db(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fact_orders_kaspi'"
        ).fetchone()
        if not table:
            logger.warning("DB missing fact_orders_kaspi table; falling back to CRM")
            return []

        query = """
            SELECT
                order_id,
                store_code,
                kaspi_offer_name,
                sku_key,
                sku_id,
                quantity,
                assigned_size,
                my_size,
                planned_shipment_date,
                kaspi_status,
                kaspi_status_detail,
                internal_status,
                signature_required,
                courier_transmission_date
            FROM fact_orders_kaspi
            WHERE (
                (assigned_size IS NOT NULL AND assigned_size != '')
                OR (my_size IS NOT NULL AND my_size != '')
            )
        """
        params: list[str] = []
        if order_id_filter:
            placeholders = ",".join(["?"] * len(order_id_filter))
            query += f" AND order_id IN ({placeholders})"
            params.extend(sorted(order_id_filter))
        else:
            query += " AND planned_shipment_date <= ?"
            params.append(target_date.isoformat())
            if lookback_days is not None:
                min_date = (target_date - timedelta(days=lookback_days)).isoformat()
                query += " AND planned_shipment_date >= ?"
                params.append(min_date)

        rows = _drop_placeholder_db_shadow_rows(conn.execute(query, params).fetchall())
        kaspi_core_maps = load_active_kaspi_name_core_maps(
            conn,
            sku_keys={_coerce_str(row["sku_key"]) for row in rows},
            store_offer_pairs={
                (_coerce_str(row["store_code"]), _coerce_str(row["kaspi_offer_name"]))
                for row in rows
            },
        )
        order_core_overrides = load_order_name_core_overrides()

    orders: list[OrderItem] = []
    db_orders: list[OrderItem] = []
    db_orders: list[OrderItem] = []
    skipped_no_size = 0
    skipped_no_date = 0

    for row in rows:
        order_id = _coerce_str(row["order_id"])
        if order_id.endswith(".0"):
            order_id = order_id[:-2]
        if not order_id or order_id == "0":
            continue

        size = _pick_size(row["assigned_size"], row["my_size"])
        if not size:
            skipped_no_size += 1
            continue

        planned_date = parse_date(row["planned_shipment_date"])
        if not planned_date:
            skipped_no_date += 1
            continue

        stage = classify_kaspi_stage_from_db_row(row)
        if stage not in {
            StageCode.ACCEPTED_PENDING_ASSEMBLY,
            StageCode.ASSEMBLED_PENDING_HANDOVER,
        } and not _is_legacy_db_ready_for_waybill(row):
            continue

        kaspi_offer_name = _coerce_str(row["kaspi_offer_name"])
        sku_key = _coerce_str(row["sku_key"])
        sku_id = _coerce_str(row["sku_id"])
        preferred_core = order_core_overrides.get(order_id, "")

        resolution = resolve_kaspi_name_core(
            store_code=row["store_code"],
            kaspi_offer_name=kaspi_offer_name,
            sku_key=sku_key,
            sku_id=sku_id,
            maps=kaspi_core_maps,
            preferred_core=preferred_core,
            preferred_source="forced_core" if preferred_core else "preferred_core",
            extract_fallback=extract_name_core,
        )
        kaspi_name_core = resolution.core or "UNKNOWN"

        quantity = row["quantity"] if row["quantity"] is not None else 1

        item = OrderItem(
            order_id=order_id,
            store_name=normalize_store_display(row["store_code"]),
            kaspi_name_core=kaspi_name_core,
            my_size=size,
            sku_key=sku_key,
            sku_id=sku_id,
            quantity=int(quantity),
            kaspi_offer_name=kaspi_offer_name,
            planned_date=planned_date,
            kaspi_name_core_source=resolution.source,
        )
        orders.append(item)

    if order_id_filter:
        logger.info(
            f"Read {len(orders)} orders from DB with size decisions "
            f"(API order-id selection: {len(order_id_filter)})"
        )
    elif lookback_days is not None:
        min_date = target_date - timedelta(days=lookback_days)
        logger.info(
            f"Read {len(orders)} orders from DB with size decisions "
            f"(date range {min_date} to {target_date})"
        )
    else:
        logger.info(
            f"Read {len(orders)} orders from DB with size decisions (date <= {target_date})"
        )
    if skipped_no_size:
        logger.info(f"Skipped {skipped_no_size} DB rows without size")
    if skipped_no_date:
        logger.info(f"Skipped {skipped_no_date} DB rows without planned date")

    return orders


def read_crm_orders(
    crm_path: Path,
    sheet_name: str,
    target_date: date = None,
    order_id_filter: Optional[set[str]] = None,
    historical_fallback_order_ids: Optional[set[str]] = None,
    lookback_days: Optional[int] = None,
    apply_date_filter: bool = True,
    crm_df: Optional[pd.DataFrame] = None,
) -> list[OrderItem]:
    """
    Read orders from CRM Excel file.

    The waybill/WhatsApp workflow must act only on sizes manually assigned in
    the current CRM batch view for the target date.

    Filters for orders where:
    - Date == target_date when the workbook has a Date column
    - MY_SIZE is filled (not empty)
    - PLANNED_SHIPPING_DATE within [target_date - lookback_days, target_date] (if specified)

    Returns list of OrderItem objects.
    """
    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    df = crm_df
    if df is None:
        logger.info(f"Reading CRM from {crm_path}")
        df = pd.read_excel(crm_path, sheet_name=sheet_name)

    if target_date:
        df, operational_stats = select_operational_crm_rows_with_targeted_fallback(
            df,
            target_date=target_date,
            order_id_filter=order_id_filter,
            historical_fallback_order_ids=historical_fallback_order_ids,
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
            f"overdue_size_backfilled={operational_stats['overdue_my_size_backfilled_rows']} "
            f"targeted_fallback_requested={operational_stats.get('targeted_fallback_orders_requested', 0)} "
            f"targeted_fallback_selected={operational_stats.get('targeted_fallback_orders_selected', 0)}"
        )

    status_col = None
    for name in ("Статус", "STATUS", "Status"):
        if name in df.columns:
            status_col = name
            break
    signature_col = None
    for name in ("Требуется подписание", "Signature Required"):
        if name in df.columns:
            signature_col = name
            break

    orders = []
    skipped_no_size = 0
    skipped_date = 0
    skipped_no_date = 0
    skipped_not_target = 0
    skipped_wrong_status = 0
    skipped_signature_required = 0
    skipped_unknown_core = 0

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
        if order_id in ("", "0"):
            continue
        if order_id_filter is not None and order_id not in order_id_filter:
            skipped_not_target += 1
            continue
        if order_id_filter is None and status_col is not None:
            if not _is_ready_status(row.get(status_col)):
                skipped_wrong_status += 1
                continue
        if order_id_filter is None and signature_col is not None:
            if _is_signature_required(row.get(signature_col)):
                skipped_signature_required += 1
                continue

        # Get planned date
        planned_date = parse_date(row.get('PLANNED_SHIPPING_DATE'))
        if not planned_date:
            planned_date = parse_date(row.get('Плановая дата передачи курьеру'))

        # Filter by date window (skip if API already filtered order IDs)
        if apply_date_filter and target_date:
            if not planned_date:
                skipped_no_date += 1
                continue
            if planned_date > target_date:
                skipped_date += 1
                continue
            if lookback_days is not None:
                min_date = target_date - timedelta(days=lookback_days)
                if planned_date < min_date:
                    skipped_date += 1
                    continue

        # Get store name
        store_name = row.get('STORE_NAME')
        if pd.isna(store_name):
            store_name = row.get('Склад передачи КД')
        store_name = normalize_store_name(store_name)

        # Get other fields
        sku_key = str(row.get('SKU_key', '')).strip()
        if sku_key.lower() == 'nan':
            sku_key = ""

        sku_id = str(row.get('SKU_ID', '')).strip()
        if sku_id.lower() == 'nan':
            sku_id = ""

        quantity = int(row.get('Quantity', 1)) if not pd.isna(row.get('Quantity')) else 1

        kaspi_offer_name = str(row.get('KASPI_OFFER_NAME', '')).strip()
        if kaspi_offer_name.lower() == 'nan':
            kaspi_offer_name = ""

        kaspi_name_core = str(row.get('Kaspi_name_core', '')).strip()
        if not kaspi_name_core or kaspi_name_core.lower() == 'nan':
            kaspi_name_core = extract_name_core(kaspi_offer_name) if kaspi_offer_name else ""
        if not kaspi_name_core or kaspi_name_core.lower() == "unknown":
            skipped_unknown_core += 1
            continue

        item = OrderItem(
            order_id=order_id,
            store_name=store_name,
            kaspi_name_core=kaspi_name_core,
            my_size=my_size,
            sku_key=sku_key,
            sku_id=sku_id,
            quantity=quantity,
            kaspi_offer_name=kaspi_offer_name,
            planned_date=planned_date,
            source_row_id=(
                f"{order_id}@{row.get('_batch_date') or target_date}#"
                f"{row.get('_row_ordinal', row.name)}"
            ),
        )
        orders.append(item)

    logger.info(f"Read {len(orders)} orders with MY_SIZE filled")
    logger.info(f"Skipped {skipped_no_size} orders without MY_SIZE")
    if apply_date_filter:
        if skipped_no_date:
            logger.info(f"Skipped {skipped_no_date} orders without planned date")
        logger.info(f"Skipped {skipped_date} orders outside planned date window")
    if order_id_filter is not None:
        logger.info(f"Skipped {skipped_not_target} orders not in target set")
    if order_id_filter is None:
        if skipped_wrong_status:
            logger.info(f"Skipped {skipped_wrong_status} orders with wrong status")
        if skipped_signature_required:
            logger.info(f"Skipped {skipped_signature_required} orders requiring signature")
    if skipped_unknown_core:
        logger.info(f"Skipped {skipped_unknown_core} orders without usable Kaspi_name_core")

    return orders


def ensure_pdf_merger() -> None:
    """Ensure PDF merge dependency is available (pypdf preferred)."""
    try:
        import pypdf  # noqa: F401
        return
    except Exception:
        try:
            import PyPDF2  # noqa: F401
            return
        except Exception:
            logger.warning("Missing PDF merge dependency. Installing pypdf...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", "pypdf"],
                    check=True,
                )
            except Exception as exc:
                raise RuntimeError(
                    "pypdf/PyPDF2 is required for PDF merging. "
                    "Install with: python3 -m pip install pypdf"
                ) from exc


def enrich_orders_with_crm(
    db_orders: list[OrderItem],
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    lookback_days: Optional[int] = None,
    apply_date_filter: bool = True,
    crm_df: Optional[pd.DataFrame] = None,
) -> list[OrderItem]:
    """Use CRM rows to enrich grouping fields (Kaspi_name_core, MY_SIZE, qty)."""
    if not db_orders:
        return []
    if crm_df is None:
        logger.warning(
            "CRM workbook unavailable; using DB-first order rows without CRM enrichment."
        )
        return db_orders

    order_ids = {o.order_id for o in db_orders}
    crm_orders = read_crm_orders(
        crm_path,
        sheet_name,
        target_date,
        order_id_filter=order_ids,
        lookback_days=lookback_days,
        apply_date_filter=apply_date_filter,
        crm_df=crm_df,
    )
    if not crm_orders:
        return db_orders

    crm_by_id: dict[str, list[OrderItem]] = defaultdict(list)
    for item in crm_orders:
        crm_by_id[item.order_id].append(item)

    db_by_id: dict[str, list[OrderItem]] = defaultdict(list)
    for item in db_orders:
        db_by_id[item.order_id].append(item)

    merged: list[OrderItem] = []
    for order_id in order_ids:
        if order_id in crm_by_id:
            merged.extend(crm_by_id[order_id])
        else:
            merged.extend(db_by_id.get(order_id, []))

    logger.info(
        f"Enriched {len(crm_by_id)} orders from CRM for grouping fields"
    )
    return merged


def get_crm_missing_info(
    crm_path: Path,
    sheet_name: str,
    target_date: date,
    order_ids: set[str],
    lookback_days: Optional[int] = None,
    crm_df: Optional[pd.DataFrame] = None,
) -> tuple[set[str], set[str]]:
    """
    Return (missing_in_crm, missing_size) for target_date.

    missing_in_crm: order_ids not present in the current operational CRM batch view.
    missing_size: order_ids present in the operational CRM batch view but still
    unresolved after overdue-size backfill.
    """
    if not crm_path.exists() or not order_ids:
        return set(order_ids), set()

    df = crm_df
    if df is None:
        try:
            df = pd.read_excel(crm_path, sheet_name=sheet_name)
        except Exception as exc:
            logger.warning(
                "CRM workbook unavailable; skipping CRM missing-size diagnostics "
                f"for DB-first waybill build: {exc}"
            )
            return set(), set()
    df, _ = select_operational_crm_rows(
        df,
        target_date=target_date,
        order_id_filter=order_ids,
        allow_historical_fallback=False,
        backfill_overdue_my_size_from_history=True,
    )
    missing_in_crm = set(order_ids)
    missing_size = set()

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
        if order_id in ("", "0"):
            continue

        if order_id not in order_ids:
            continue

        # Filter by date window
        planned_date = parse_date(row.get('PLANNED_SHIPPING_DATE'))
        if not planned_date:
            planned_date = parse_date(row.get('Плановая дата передачи курьеру'))
        if not planned_date:
            continue
        if planned_date > target_date:
            continue
        if lookback_days is not None:
            min_date = target_date - timedelta(days=lookback_days)
            if planned_date < min_date:
                continue

        missing_in_crm.discard(order_id)

        # Check MY_SIZE
        my_size = str(row.get('MY_SIZE', '')).strip()
        if not my_size or my_size.lower() in ('nan', 'none', ''):
            missing_size.add(order_id)

    return missing_in_crm, missing_size


def load_waybills_from_folder(
    waybill_folder: Path,
    order_id_filter: Optional[set[str]] = None,
) -> dict[str, Path]:
    """
    Load waybill PDFs from a folder (downloaded via API).

    Expects files named {order_id}.pdf or KASPI_SHOP-{order_id}.pdf.

    Returns dict mapping order_id -> PDF path.
    """
    waybill_map = {}

    if not waybill_folder.exists():
        logger.debug(f"Waybill folder does not exist: {waybill_folder}")
        return waybill_map

    pdf_files = list(waybill_folder.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files in {waybill_folder}")

    for pdf_path in pdf_files:
        basename = pdf_path.name

        # Try KASPI_SHOP-{order_id}.pdf pattern
        match = re.search(WAYBILL_PATTERN, basename)
        if match:
            order_id = match.group(1)
            if order_id_filter is not None and order_id not in order_id_filter:
                continue
            waybill_map[order_id] = pdf_path
            continue

        # Try {order_id}.pdf pattern (downloaded via API)
        if basename.endswith('.pdf'):
            potential_order_id = basename[:-4]  # Remove .pdf
            if potential_order_id.isdigit():
                if (
                    order_id_filter is not None
                    and potential_order_id not in order_id_filter
                ):
                    continue
                waybill_map[potential_order_id] = pdf_path

    logger.info(f"Loaded {len(waybill_map)} waybills from folder")
    return waybill_map


def extract_waybills_from_zips(
    zip_dir: Path,
    temp_dir: Path,
    pattern: str = "waybill*.zip",
    order_id_filter: Optional[set[str]] = None,
) -> dict[str, Path]:
    """
    Extract waybill PDFs from all ZIP files in directory.

    Returns dict mapping order_id -> PDF path.
    """
    waybill_map = {}

    zip_files = list(zip_dir.glob(pattern))
    logger.info(f"Found {len(zip_files)} waybill ZIP files")

    for zip_path in zip_files:
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for filename in zf.namelist():
                    if filename.endswith('/') or not filename.lower().endswith('.pdf'):
                        continue

                    basename = Path(filename).name
                    match = re.search(WAYBILL_PATTERN, basename)

                    if match:
                        order_id = match.group(1)
                        if order_id_filter is not None and order_id not in order_id_filter:
                            continue
                        extracted_path = temp_dir / basename

                        # Only extract if not already extracted
                        if not extracted_path.exists():
                            with zf.open(filename) as src:
                                with open(extracted_path, 'wb') as dst:
                                    dst.write(src.read())

                        waybill_map[order_id] = extracted_path
        except Exception as e:
            logger.warning(f"Error extracting {zip_path}: {e}")

    logger.info(f"Extracted {len(waybill_map)} waybill PDFs from ZIPs")
    return waybill_map


def load_all_waybills(
    waybill_dir: Path,
    temp_dir: Path,
    waybill_folder_name: str = "waybills",
    order_id_filter: Optional[set[str]] = None,
) -> dict[str, Path]:
    """
    Load waybills from both folder (API downloads) and ZIP files.

    Priority: folder first, then ZIP extraction (folder takes precedence).

    Returns dict mapping order_id -> PDF path.
    """
    waybill_map = {}

    # 1. First, extract from ZIP files
    waybill_map.update(
        extract_waybills_from_zips(
            waybill_dir,
            temp_dir,
            order_id_filter=order_id_filter,
        )
    )

    # 2. Then, load from waybills folder (overrides ZIP if exists)
    waybill_folder = waybill_dir / waybill_folder_name
    folder_waybills = load_waybills_from_folder(
        waybill_folder,
        order_id_filter=order_id_filter,
    )
    waybill_map.update(folder_waybills)

    logger.info(f"Total waybills available: {len(waybill_map)}")
    return waybill_map


def group_orders(
    orders: list[OrderItem],
    waybill_map: dict[str, Path]
) -> tuple[list[WaybillGroup], list[OrderItem]]:
    """
    Group orders into NORMAL, MULTI_QTY, and MULTI_LINE groups.

    Returns (groups, missing_orders).
    """
    groups = []
    missing = []

    # Index orders by order_id
    by_order_id = defaultdict(list)
    for order in orders:
        by_order_id[order.order_id].append(order)

    # Identify multi-line order IDs
    multi_line_ids = {oid for oid, items in by_order_id.items() if len(items) > 1}

    # MULTI_LINE: Same order_id, multiple different products (one PDF per order)
    for order_id in multi_line_ids:
        items = by_order_id[order_id]
        pdf_path = waybill_map.get(order_id)
        if not pdf_path:
            missing.extend(items)
            continue
        store_name = items[0].store_name
        group = WaybillGroup(
            group_type="MULTI_LINE",
            store_name=store_name,
            items=items,
            pdf_path=pdf_path,
            pdf_paths=[pdf_path],
        )
        groups.append(group)

    # MULTI_QTY: quantity > 1, one PDF per order (exclude multi-line)
    for order_id, items in by_order_id.items():
        if order_id in multi_line_ids:
            continue
        if not items:
            continue
        item = items[0]
        if item.quantity <= 1:
            continue
        pdf_path = waybill_map.get(order_id)
        if not pdf_path:
            missing.extend(items)
            continue
        store_name = item.store_name
        group = WaybillGroup(
            group_type="MULTI_QTY",
            store_name=store_name,
            items=[item],
            pdf_path=pdf_path,
            pdf_paths=[pdf_path],
        )
        groups.append(group)

    # NORMAL: quantity == 1, group by (store, kaspi_name_core, my_size)
    normal_groups: dict[tuple[str, str, str], list[OrderItem]] = defaultdict(list)
    for order_id, items in by_order_id.items():
        if order_id in multi_line_ids:
            continue
        if not items:
            continue
        item = items[0]
        if item.quantity != 1:
            continue
        key = (item.store_name, item.kaspi_name_core, item.my_size)
        normal_groups[key].append(item)

    for (store_name, _, _), items in normal_groups.items():
        # De-duplicate by order_id to avoid double counting
        unique_items: dict[str, OrderItem] = {}
        for item in items:
            if item.order_id and item.order_id not in unique_items:
                unique_items[item.order_id] = item

        pdf_paths = []
        grouped_items: list[OrderItem] = []
        for item in unique_items.values():
            pdf_path = waybill_map.get(item.order_id)
            if pdf_path:
                pdf_paths.append(pdf_path)
                grouped_items.append(item)
            else:
                missing.append(item)
        if not pdf_paths:
            continue
        group = WaybillGroup(
            group_type="NORMAL",
            store_name=store_name,
            items=grouped_items,
            pdf_path=pdf_paths[0],
            pdf_paths=pdf_paths,
        )
        groups.append(group)

    logger.info(f"Grouped into {len(groups)} bundles, {len(missing)} missing waybills")
    return groups, missing


def generate_filename(group: WaybillGroup, index: int) -> str:
    """Generate output filename based on group type."""
    name_core = sanitize_filename(group.kaspi_name_core)
    size = sanitize_filename(group.my_size)

    if group.group_type == "NORMAL":
        # {kaspi_name_core}_{MY_SIZE}-{COUNT}.pdf (count = number of orders)
        count = len(group.pdf_paths) if group.pdf_paths else group.total_quantity
        return f"{name_core}_{size}-{count}.pdf"

    elif group.group_type == "MULTI_QTY":
        return f"Местовая-{index})_{name_core}-{size}-{group.total_quantity}.pdf"

    elif group.group_type == "MULTI_LINE":
        parts = [format_item_detail(item) for item in group.items]
        return f"Местовая-{index})_{'_'.join(parts)}.pdf"

    return f"unknown_{group.order_id}.pdf"


def size_sort_key(size: str) -> int:
    """Get sort key for size."""
    return SIZE_ORDER.get(size.upper(), 99)


def manifest_sort_key(group: WaybillGroup) -> tuple:
    """Sort key for manifest: name_core -> size -> sku_key -> sku_id."""
    return (
        group.kaspi_name_core or "",
        size_sort_key(group.my_size),
        group.sku_key or "",
        group.sku_id or "",
    )


def _category_name_for_group(group: WaybillGroup) -> str:
    output_filename = str(group.output_filename or "").replace("\\", "/")
    if output_filename:
        return Path(output_filename).parent.name
    return {
        "NORMAL": "NORMAL_singles",
        "MULTI_QTY": "SPECIAL_multi_qty",
        "MULTI_LINE": "SPECIAL_multi_line",
    }.get(group.group_type, group.group_type or "UNKNOWN")


def _ordering_tokens(value: str) -> list[str]:
    text = sanitize_filename(value).upper()
    if not text:
        return []
    return [token for token in re.split(r"[_\-]+", text) if token]


def _ordering_color_key(value: str) -> str:
    for token in _ordering_tokens(value):
        if token in ORDERING_COLOR_TOKENS:
            return token
    return ""


def _ordering_family_key(value: str) -> str:
    tokens = [
        token
        for token in _ordering_tokens(value)
        if token not in ORDERING_COLOR_TOKENS
        and token not in ORDERING_NOISE_TOKENS
        and token not in SIZE_ORDER
    ]
    if not tokens:
        tokens = _ordering_tokens(value)
    if not tokens:
        return "UNKNOWN"
    return "_".join(tokens[:4])


def _group_size_token(group: WaybillGroup) -> str:
    return sanitize_filename(group.my_size).upper()


def stable_group_sort_key(group: WaybillGroup) -> tuple:
    """Deterministic tie-breaker for send ordering and special bundle numbering."""
    product_label = sanitize_filename(group.kaspi_name_core or group.sku_key or group.sku_id or "UNKNOWN")
    return (
        tuple(group.order_ids),
        sanitize_filename(group.store_name or ""),
        sanitize_filename(group.group_type or ""),
        size_sort_key(group.my_size),
        sanitize_filename(group.my_size).upper(),
        _ordering_family_key(product_label),
        _ordering_color_key(product_label),
        sanitize_filename(group.kaspi_name_core or ""),
        sanitize_filename(group.sku_key or ""),
        sanitize_filename(group.sku_id or ""),
        tuple(sorted(format_item_detail(item) for item in group.items)),
    )


def _build_send_entry_metadata(group: WaybillGroup, base_order: int) -> dict[str, Any]:
    product_label = sanitize_filename(group.kaspi_name_core or group.sku_key or group.sku_id or "UNKNOWN")
    size_token = _group_size_token(group)
    size_rank = size_sort_key(size_token) if size_token else 99
    stable_order_key = stable_group_sort_key(group)
    item_family_keys = {
        _ordering_family_key(item.kaspi_name_core or item.sku_key or item.sku_id or "")
        for item in group.items
        if (item.kaspi_name_core or item.sku_key or item.sku_id)
    }
    multi_line_mixed = group.group_type == "MULTI_LINE" and len(item_family_keys) > 1
    product_family_key = (
        f"MULTI_LINE::{stable_order_key!r}"
        if multi_line_mixed
        else _ordering_family_key(product_label)
    )
    color_key = "" if multi_line_mixed else _ordering_color_key(product_label)
    product_color_key = (
        f"MULTI_LINE::{stable_order_key!r}"
        if group.group_type == "MULTI_LINE"
        else product_label.upper()
    )
    return {
        "base_order": base_order,
        "stable_order_key": stable_order_key,
        "category": _category_name_for_group(group),
        "size_token": size_token,
        "size_rank": size_rank,
        "product_family_key": product_family_key,
        "color_key": color_key,
        "product_color_key": product_color_key,
    }


def _order_send_category_entries(
    entries_meta: list[dict[str, Any]],
    *,
    prioritize_video_bundles: bool = False,
) -> list[dict[str, Any]]:
    if not entries_meta:
        return []

    category_name = str(entries_meta[0].get("category") or "")
    if category_name == "SPECIAL_multi_line":
        return sorted(
            entries_meta,
            key=lambda meta: (
                tuple(meta.get("stable_order_key") or ()),
                str(meta["entry"].get("filename") or "").lower(),
            ),
        )

    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    first_seen: dict[str, tuple] = {}
    family_by_block: dict[str, str] = {}
    for meta in entries_meta:
        block_key = str(meta.get("product_color_key") or meta["entry"].get("pdf_key") or meta["base_order"])
        blocks[block_key].append(meta)
        stable_key = tuple(meta.get("stable_order_key") or ())
        current = first_seen.get(block_key)
        if current is None or stable_key < current:
            first_seen[block_key] = stable_key
        family_by_block.setdefault(
            block_key,
            str(meta.get("product_family_key") or block_key),
        )

    for items in blocks.values():
        items.sort(
            key=lambda meta: (
                int(meta.get("size_rank", 99)),
                str(meta.get("size_token") or "").upper(),
                tuple(meta.get("stable_order_key") or ()),
                str(meta["entry"].get("filename") or "").lower(),
            )
        )

    remaining = set(blocks.keys())
    ordered: list[dict[str, Any]] = []
    previous_family = ""

    def _block_priority(block_key: str) -> int:
        if not prioritize_video_bundles or category_name != "NORMAL_singles":
            return 1
        family_key = str(family_by_block.get(block_key, "")).upper()
        return 0 if family_key in SEND_PRIORITY_FAMILY_ALIASES else 1

    while remaining:
        candidate_blocks = [
            block_key
            for block_key in remaining
            if family_by_block.get(block_key, "") != previous_family
        ] or list(remaining)
        next_block = min(
            candidate_blocks,
            key=lambda block_key: (
                _block_priority(block_key),
                first_seen.get(block_key, ()),
                str(blocks[block_key][0]["entry"].get("filename") or "").lower(),
                block_key,
            ),
        )
        ordered.extend(blocks[next_block])
        previous_family = family_by_block.get(next_block, "")
        remaining.remove(next_block)

    return ordered


def _assign_send_sequence(entries_meta: list[dict[str, Any]]) -> None:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for meta in entries_meta:
        by_category[str(meta.get("category") or "")].append(meta)

    prioritize_video_bundles = bool(
        by_category.get("SPECIAL_multi_line") or by_category.get("SPECIAL_multi_qty")
    )
    send_sequence = 1
    for category in sorted(
        by_category.keys(),
        key=lambda category: (
            SEND_CATEGORY_PRIORITY.get(category, 99),
            category.lower(),
        ),
    ):
        for meta in _order_send_category_entries(
            by_category[category],
            prioritize_video_bundles=prioritize_video_bundles,
        ):
            entry = meta["entry"]
            entry["send_sequence"] = send_sequence
            send_sequence += 1


def _special_send_filename_indices(groups: list[WaybillGroup]) -> dict[int, int]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for base_order, group in enumerate(groups, start=1):
        metadata = _build_send_entry_metadata(group, base_order)
        category = str(metadata.get("category") or "")
        if category not in {"SPECIAL_multi_line", "SPECIAL_multi_qty"}:
            continue
        preview_index = base_order if group.group_type != "NORMAL" else 0
        by_category[category].append(
            {
                "group": group,
                "entry": {"filename": generate_filename(group, preview_index)},
                **metadata,
            }
        )

    overrides: dict[int, int] = {}
    next_index = 1
    for category in sorted(
        by_category.keys(),
        key=lambda category: (
            SEND_CATEGORY_PRIORITY.get(category, 99),
            category.lower(),
        ),
    ):
        for meta in _order_send_category_entries(by_category[category]):
            overrides[id(meta["group"])] = next_index
            next_index += 1
    return overrides


def is_heavy_item(item: OrderItem) -> bool:
    """Check if item is heavy (requires separate package)."""
    return (
        item.kaspi_name_core in HEAVY_ITEMS or
        item.sku_key in HEAVY_ITEMS or
        item.sku_id in HEAVY_ITEMS
    )


def count_packages(groups: list[WaybillGroup]) -> int:
    """
    Count total packages for a list of groups.

    Rules:
    - NORMAL: 1 package each
    - MULTI_QTY: qty <= 3 and not heavy = 1 package, else = qty packages
    - MULTI_LINE: if total qty <= 3 and no heavy items = 1 package, else split
    """
    packages = 0

    for group in groups:
        if group.group_type == "NORMAL":
            packages += 1

        elif group.group_type == "MULTI_QTY":
            item = group.items[0]
            if item.quantity <= 3 and not is_heavy_item(item):
                packages += 1
            else:
                packages += item.quantity

        elif group.group_type == "MULTI_LINE":
            heavy_count = sum(1 for item in group.items if is_heavy_item(item))
            total_qty = group.total_quantity

            if total_qty <= 3 and heavy_count == 0:
                packages += 1
            else:
                light_items = len(group.items) - heavy_count
                packages += heavy_count + (1 if light_items > 0 else 0)

    return packages


def is_overdue_group(group: WaybillGroup, target_date: date) -> bool:
    """Return True if any planned date is before target_date."""
    planned_dates = [item.planned_date for item in group.items if item.planned_date]
    if not planned_dates:
        return False
    return min(planned_dates) < target_date


def split_groups_by_overdue(
    groups_by_store: dict[str, list[WaybillGroup]],
    target_date: date,
) -> tuple[dict[str, list[WaybillGroup]], dict[str, list[WaybillGroup]]]:
    """Split groups into (today, overdue) by planned date."""
    today: dict[str, list[WaybillGroup]] = defaultdict(list)
    overdue: dict[str, list[WaybillGroup]] = defaultdict(list)

    for store, groups in groups_by_store.items():
        for group in groups:
            if is_overdue_group(group, target_date):
                overdue[store].append(group)
            else:
                today[store].append(group)

    return dict(today), dict(overdue)


def _group_pdf_paths(group: WaybillGroup) -> list[Path]:
    """Return unique PDF paths for a group, preserving order."""
    pdf_paths = group.pdf_paths or ([group.pdf_path] if group.pdf_path else [])
    result: list[Path] = []
    seen: set[str] = set()
    for pdf_path in pdf_paths:
        if not pdf_path:
            continue
        key = str(pdf_path)
        if key in seen:
            continue
        seen.add(key)
        result.append(pdf_path)
    return result


def clone_waybill_group(group: WaybillGroup) -> WaybillGroup:
    """Clone group metadata so secondary outputs don't overwrite primary logs."""
    return WaybillGroup(
        group_type=group.group_type,
        store_name=group.store_name,
        items=list(group.items),
        pdf_path=group.pdf_path,
        pdf_paths=list(group.pdf_paths),
    )


def build_cross_store_groups(groups: list[WaybillGroup]) -> list[WaybillGroup]:
    """
    Build merged grouping across stores.

    - NORMAL groups are merged by (kaspi_name_core, my_size) across all stores.
    - MULTI_QTY and MULTI_LINE remain one-group-per-order (cloned).
    """
    merged_groups: list[WaybillGroup] = []
    normal_buckets: dict[tuple[str, str], list[WaybillGroup]] = defaultdict(list)

    for group in groups:
        if group.group_type == "NORMAL":
            normal_buckets[(group.kaspi_name_core, group.my_size)].append(group)
        else:
            merged_groups.append(clone_waybill_group(group))

    for _, bucket in normal_buckets.items():
        items: list[OrderItem] = []
        seen_order_ids: set[str] = set()
        pdf_paths: list[Path] = []
        seen_pdf_paths: set[str] = set()

        for group in bucket:
            for item in group.items:
                order_id = item.order_id or ""
                if order_id and order_id in seen_order_ids:
                    continue
                if order_id:
                    seen_order_ids.add(order_id)
                items.append(item)

            for pdf_path in _group_pdf_paths(group):
                path_key = str(pdf_path)
                if path_key in seen_pdf_paths:
                    continue
                seen_pdf_paths.add(path_key)
                pdf_paths.append(pdf_path)

        if not items or not pdf_paths:
            continue

        merged_groups.append(
            WaybillGroup(
                group_type="NORMAL",
                store_name="MERGED",
                items=items,
                pdf_path=pdf_paths[0],
                pdf_paths=pdf_paths,
            )
        )

    return merged_groups


def build_store_output(
    store_name: str,
    groups: list[WaybillGroup],
    base_output_dir: Path,
    date_prefix: str,
    dry_run: bool = False,
    send_batch_order_labels: bool = False,
) -> dict:
    """
    Build output directory for one store.

    Creates:
    - {DD.MM.YY}_{STORE}_qnt{total}/
        - NORMAL_singles/
        - SPECIAL_multi_line/
        - SPECIAL_multi_qty/
        - manifest_normal_singles.csv
        - manifest_special_multi_line.csv
        - manifest_special_multi_qty.csv
    """
    total_qty = sum(g.total_quantity for g in groups)
    folder_name = f"{date_prefix}_{store_name}_qnt{total_qty}"
    if send_batch_order_labels:
        store_dir = allocate_immutable_send_batch_dir(base_output_dir, folder_name)
    else:
        store_dir = base_output_dir / folder_name

    stats = {
        'normal': 0,
        'multi_qty': 0,
        'multi_line': 0,
        'packages': count_packages(groups),
        'batch_dir': store_dir,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create {store_dir}")
        return stats

    # Group by type
    normal_groups = [g for g in groups if g.group_type == "NORMAL"]
    multi_qty_groups = [g for g in groups if g.group_type == "MULTI_QTY"]
    multi_line_groups = [g for g in groups if g.group_type == "MULTI_LINE"]

    # Create directories (only for non-empty groups)
    store_dir.mkdir(parents=True, exist_ok=True)
    normal_dir = store_dir / "NORMAL_singles" if normal_groups else None
    multi_line_dir = store_dir / "SPECIAL_multi_line" if multi_line_groups else None
    multi_qty_dir = store_dir / "SPECIAL_multi_qty" if multi_qty_groups else None
    if normal_dir:
        normal_dir.mkdir(parents=True, exist_ok=True)
    if multi_line_dir:
        multi_line_dir.mkdir(parents=True, exist_ok=True)
    if multi_qty_dir:
        multi_qty_dir.mkdir(parents=True, exist_ok=True)

    # Sort each type
    normal_groups.sort(key=manifest_sort_key)
    multi_qty_groups.sort(key=manifest_sort_key)
    multi_line_groups.sort(key=manifest_sort_key)
    special_filename_indices = (
        _special_send_filename_indices(groups) if send_batch_order_labels else {}
    )

    used_filenames: set[str] = set()

    def ensure_unique(filename: str, order_id: str) -> str:
        """Ensure filename uniqueness within the store output."""
        if filename not in used_filenames:
            used_filenames.add(filename)
            return filename
        stem, ext = os.path.splitext(filename)
        suffix = order_id or "dup"
        candidate = f"{stem}_{suffix}{ext}"
        counter = 2
        while candidate in used_filenames:
            candidate = f"{stem}_{suffix}_{counter}{ext}"
            counter += 1
        used_filenames.add(candidate)
        return candidate

    # Process NORMAL
    for group in normal_groups:
        filename = generate_filename(group, 0)
        filename = ensure_unique(filename, group.order_id)
        output_path = normal_dir / filename
        group.output_filename = f"NORMAL_singles/{filename}"

        pdf_paths = group.pdf_paths or ([group.pdf_path] if group.pdf_path else [])
        if pdf_paths:
            merge_pdfs(pdf_paths, output_path)
            stats['normal'] += 1

    # Process MULTI_QTY
    for i, group in enumerate(multi_qty_groups, 1):
        display_index = special_filename_indices.get(id(group), i)
        filename = generate_filename(group, display_index)
        filename = ensure_unique(filename, group.order_id)
        output_path = multi_qty_dir / filename
        group.output_filename = f"SPECIAL_multi_qty/{filename}"

        pdf_paths = group.pdf_paths or ([group.pdf_path] if group.pdf_path else [])
        if pdf_paths:
            merge_pdfs(pdf_paths, output_path)
            stats['multi_qty'] += 1

    # Process MULTI_LINE
    for i, group in enumerate(multi_line_groups, 1):
        display_index = special_filename_indices.get(id(group), i)
        filename = generate_filename(group, display_index)
        filename = ensure_unique(filename, group.order_id)
        output_path = multi_line_dir / filename
        group.output_filename = f"SPECIAL_multi_line/{filename}"

        pdf_paths = group.pdf_paths or ([group.pdf_path] if group.pdf_path else [])
        if pdf_paths:
            merge_pdfs(pdf_paths, output_path)
            stats['multi_line'] += 1

    # Generate manifests
    write_manifest(normal_groups, store_dir / "manifest_normal_singles.csv", "NORMAL")
    write_manifest(multi_qty_groups, store_dir / "manifest_special_multi_qty.csv", "MULTI_QTY")
    write_manifest(multi_line_groups, store_dir / "manifest_special_multi_line.csv", "MULTI_LINE")

    return stats


def allocate_immutable_send_batch_dir(base_output_dir: Path, folder_name: str) -> Path:
    """Allocate a unique immutable SEND batch directory, preserving older rebuilds."""
    candidate = base_output_dir / folder_name
    if not candidate.exists():
        return candidate

    revision = 2
    while True:
        revised = base_output_dir / f"{folder_name}_r{revision}"
        if not revised.exists():
            return revised
        revision += 1


def _parse_send_batch_date(folder_name: str) -> Optional[date]:
    match = re.match(r"^(\d{2})\.(\d{2})\.(\d{2})_", folder_name)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return date(2000 + int(year), int(month), int(day))
    except ValueError:
        return None


def _allocate_archive_destination(archive_root: Path, folder_name: str) -> Path:
    candidate = archive_root / folder_name
    if not candidate.exists():
        return candidate
    revision = 2
    while True:
        revised = archive_root / f"{folder_name}_arch{revision}"
        if not revised.exists():
            return revised
        revision += 1


def archive_past_send_batches(output_dir: Path, target_date: date) -> int:
    """
    Move past-day immutable SEND batches out of Today/ into Archive/.

    Current-day batches remain in place so rebuilds and manual resumes still work.
    """
    send_root = output_dir / "MERGED" / WHATSAPP_SEND_ROOT_NAME
    if not send_root.exists():
        return 0

    archive_root = output_dir.parent / "Archive" / "SEND"
    moved = 0
    for child in sorted(send_root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        batch_date = _parse_send_batch_date(child.name)
        if batch_date is None or batch_date >= target_date:
            continue
        day_archive_root = archive_root / batch_date.isoformat()
        day_archive_root.mkdir(parents=True, exist_ok=True)
        destination = _allocate_archive_destination(day_archive_root, child.name)
        shutil.move(str(child), str(destination))
        moved += 1
    return moved


def reset_today_output_dir(output_dir: Path, output_layout: str, *, target_date: Optional[date] = None) -> None:
    """
    Clear rebuildable Today outputs while preserving current-day immutable SEND batches.

    The operator may still be sending from an older MERGED/SEND batch while a
    fresh waybill build is running. For per-store-and-merged output we therefore
    clear PER_STORE, MERGED/TODAY, MERGED/OVERDUE, and top-level reports, but
    keep current-day MERGED/SEND batches intact so existing manifests/ledgers
    remain resumable. Older dated SEND batches are archived out of Today first.
    """
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return

    if output_layout != OUTPUT_LAYOUT_PER_STORE_AND_MERGED:
        shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    merged_root = output_dir / "MERGED"
    send_root = merged_root / WHATSAPP_SEND_ROOT_NAME
    if target_date is not None:
        archived_count = archive_past_send_batches(output_dir, target_date)
        if archived_count:
            logger.info(f"Archived {archived_count} past SEND batches out of Today/")

    for child in list(output_dir.iterdir()):
        if child == merged_root:
            merged_root.mkdir(parents=True, exist_ok=True)
            for merged_child in list(merged_root.iterdir()):
                if merged_child == send_root:
                    continue
                if merged_child.is_dir():
                    shutil.rmtree(merged_child)
                else:
                    merged_child.unlink(missing_ok=True)
            continue

        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)

    merged_root.mkdir(parents=True, exist_ok=True)


def _store_order_counts(group: WaybillGroup) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    order_store: dict[str, str] = {}
    for item in group.items:
        store_name = str(item.store_name or "").strip()
        if not store_name:
            continue

        order_id = str(item.order_id or "").strip()
        if not order_id:
            counts[store_name] += 1
            continue

        previous_store = order_store.get(order_id)
        if previous_store and previous_store != store_name:
            raise ValueError(
                f"Order {order_id} spans multiple stores in one send bundle: "
                f"{previous_store} vs {store_name}"
            )
        order_store[order_id] = store_name

    for store_name in order_store.values():
        counts[store_name] += 1
    return dict(counts)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compute_batch_hash(entries: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    stable_entries = []
    for entry in sorted(entries, key=lambda x: x["pdf_key"]):
        stable_entries.append(
            {
                "pdf_key": entry["pdf_key"],
                "relative_output_path": entry["relative_output_path"],
                "sha256": entry["sha256"],
                "file_size": entry["file_size"],
                "mtime": entry["mtime"],
                "logical_group_type": entry["logical_group_type"],
                "order_ids": entry["order_ids"],
                "source_row_ids": entry["source_row_ids"],
                "product_family_key": entry.get("product_family_key", ""),
                "color_key": entry.get("color_key", ""),
                "product_color_key": entry.get("product_color_key", ""),
                "size_token": entry.get("size_token", ""),
                "size_rank": int(entry.get("size_rank", 0) or 0),
                "send_sequence": int(entry.get("send_sequence", 0) or 0),
            }
        )
    digest.update(json.dumps(stable_entries, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def write_send_batch_manifest(
    batch_root: Path,
    today_root: Path,
    groups: list[WaybillGroup],
    target_date: date,
    expected_overdue_order_ids: Optional[set[str]] = None,
) -> Path:
    """Write immutable manifest for the operator-safe SEND batch."""
    entries: list[dict[str, Any]] = []
    entries_meta: list[dict[str, Any]] = []
    send_order_ids: set[str] = set()
    overdue_order_ids: set[str] = {str(order_id).strip() for order_id in expected_overdue_order_ids or set() if str(order_id).strip()}

    for base_order, group in enumerate(groups, start=1):
        relative_output_path = str(group.output_filename or "").replace("\\", "/")
        if not relative_output_path:
            continue
        output_path = batch_root / relative_output_path
        if not output_path.exists():
            raise FileNotFoundError(f"Manifest output missing on disk: {output_path}")

        stat = output_path.stat()
        order_ids = group.order_ids
        send_order_ids.update(order_ids)
        group_overdue = any(
            item.planned_date and item.planned_date < target_date
            for item in group.items
        )
        if group_overdue:
            overdue_order_ids.update(order_ids)

        items_detail = [format_item_detail(item) for item in group.items]
        core_resolution_sources = sorted(
            {
                str(getattr(item, "kaspi_name_core_source", "") or "").strip()
                for item in group.items
                if str(getattr(item, "kaspi_name_core_source", "") or "").strip()
            }
        )
        unsafe_core_resolution_sources = sorted(
            source for source in core_resolution_sources if source not in SAFE_KASPI_NAME_CORE_SOURCES
        )
        source_row_ids = [
            str(getattr(item, "source_row_id", "") or "").strip()
            for item in group.items
            if str(getattr(item, "source_row_id", "") or "").strip()
        ]
        sha256 = _file_sha256(output_path)
        pdf_key_seed = {
            "group_type": group.group_type,
            "order_ids": order_ids,
            "sha256": sha256,
            "items_detail": items_detail,
            "source_row_ids": source_row_ids,
        }
        pdf_key = hashlib.sha256(
            json.dumps(pdf_key_seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        metadata = _build_send_entry_metadata(group, base_order)

        entry = {
            "pdf_key": pdf_key,
            "relative_output_path": relative_output_path,
            "relative_to_today": str(output_path.relative_to(today_root)).replace("\\", "/"),
            "filename": output_path.name,
            "category": Path(relative_output_path).parent.name,
            "logical_group_type": group.group_type,
            "sha256": sha256,
            "file_size": int(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "order_ids": order_ids,
            "order_counts_by_store": _store_order_counts(group),
            "source_row_ids": source_row_ids,
            "items_detail": items_detail,
            "core_resolution_sources": core_resolution_sources,
            "unsafe_core_resolution_sources": unsafe_core_resolution_sources,
            "requires_core_review": bool(unsafe_core_resolution_sources),
        }
        entry.update({key: value for key, value in metadata.items() if key != "base_order"})
        entries.append(entry)
        entries_meta.append({"entry": entry, **metadata})

    _assign_send_sequence(entries_meta)

    payload = {
        "schema_version": 2,
        "created_at": datetime.now(ALMATY_TZ).isoformat(),
        "target_date": target_date.isoformat(),
        "today_root": str(today_root),
        "source_root": str(batch_root),
        "batch_label": batch_root.name,
        "counts": {
            "pdfs": len(entries),
            "orders": len(send_order_ids),
            "overdue_orders": len(overdue_order_ids),
        },
        "send_order_ids": sorted(send_order_ids),
        "overdue_order_ids": sorted(overdue_order_ids),
        "missing_overdue_order_ids": sorted(overdue_order_ids - send_order_ids),
        "terminal_orders_excluded": True,
        "entries": entries,
        "unsafe_core_resolution_entries": [
            {
                "pdf_key": entry["pdf_key"],
                "filename": entry["filename"],
                "order_ids": entry["order_ids"],
                "unsafe_core_resolution_sources": entry["unsafe_core_resolution_sources"],
            }
            for entry in entries
            if entry.get("requires_core_review")
        ],
    }
    payload["counts"]["unsafe_core_resolution_entries"] = len(payload["unsafe_core_resolution_entries"])
    payload["batch_hash"] = _compute_batch_hash(entries)

    output_path = batch_root / "send_batch_manifest.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (batch_root / "kaspi_name_core_resolution_report.json").write_text(
        json.dumps(
            {
                "created_at": payload["created_at"],
                "batch_label": payload["batch_label"],
                "target_date": payload["target_date"],
                "counts": {
                    "pdfs": payload["counts"]["pdfs"],
                    "unsafe_core_resolution_entries": payload["counts"]["unsafe_core_resolution_entries"],
                },
                "unsafe_core_resolution_entries": payload["unsafe_core_resolution_entries"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def write_manifest(groups: list[WaybillGroup], output_path: Path, manifest_type: str):
    """Write manifest CSV file."""
    if not groups:
        return

    fieldnames = [
        'type', 'store', 'order_id', 'kaspi_name_core', 'size',
        'sku_key', 'sku_id', 'quantity', 'kaspi_offer_name', 'output'
    ]

    if manifest_type == "MULTI_LINE":
        fieldnames.insert(4, 'items_count')
        fieldnames.append('items_detail')

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for group in groups:
            row = {
                'type': manifest_type,
                'store': group.store_name,
                'order_id': ';'.join(group.order_ids),
                'kaspi_name_core': group.kaspi_name_core,
                'size': group.my_size,
                'sku_key': group.sku_key,
                'sku_id': group.sku_id,
                'quantity': group.total_quantity,
                'kaspi_offer_name': group.items[0].kaspi_offer_name if group.items else "",
                'output': group.output_filename,
            }

            if manifest_type == "MULTI_LINE":
                row['items_count'] = len(group.items)
                detail_parts = [format_item_detail(item) for item in group.items]
                row['items_detail'] = ';'.join(detail_parts)

            writer.writerow(row)


def write_build_log(
    all_groups: list[WaybillGroup],
    missing: list[OrderItem],
    output_path: Path,
):
    """Write build_log.csv with ALL stores/orders."""
    fieldnames = [
        'type', 'store', 'order_id', 'kaspi_name_core', 'size',
        'sku_key', 'sku_id', 'quantity', 'kaspi_offer_name', 'output',
        'status', 'processed_at'
    ]

    timestamp = datetime.now().isoformat()

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Write processed groups
        for group in sorted(all_groups, key=manifest_sort_key):
            writer.writerow({
                'type': group.group_type,
                'store': group.store_name,
                'order_id': ';'.join(group.order_ids),
                'kaspi_name_core': group.kaspi_name_core,
                'size': group.my_size,
                'sku_key': group.sku_key,
                'sku_id': group.sku_id,
                'quantity': group.total_quantity,
                'kaspi_offer_name': group.items[0].kaspi_offer_name if group.items else "",
                'output': group.output_filename,
                'status': 'OK',
                'processed_at': timestamp,
            })

        # Write missing
        for item in missing:
            writer.writerow({
                'type': 'MISSING',
                'store': item.store_name,
                'order_id': item.order_id,
                'kaspi_name_core': item.kaspi_name_core,
                'size': item.my_size,
                'sku_key': item.sku_key,
                'sku_id': item.sku_id,
                'quantity': item.quantity,
                'kaspi_offer_name': item.kaspi_offer_name,
                'output': '',
                'status': 'PDF_NOT_FOUND',
                'processed_at': timestamp,
            })


def write_missing_orders(
    missing: list[OrderItem],
    output_path: Path,
    extra_missing: Optional[list[dict]] = None,
    rows: Optional[list[dict]] = None,
):
    """Write missing_orders.csv."""
    if rows is None:
        rows = collect_missing_rows(missing, extra_missing)
    if not rows:
        return

    fieldnames = ['store', 'order_id', 'kaspi_name_core', 'size', 'sku_key', 'sku_id', 'reason']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return rows


def collect_missing_rows(
    missing: list[OrderItem],
    extra_missing: Optional[list[dict]] = None,
) -> list[dict]:
    """Collect unique missing rows for CSV/logging."""
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_row(row: dict) -> None:
        oid = str(row.get('order_id', '')).strip()
        if not oid or oid == "0" or oid.lower() == "nan":
            return
        reason = str(row.get('reason', '')).strip()
        key = (oid, reason)
        if key in seen:
            return
        seen.add(key)
        rows.append({
            'store': row.get('store', ''),
            'order_id': oid,
            'kaspi_name_core': row.get('kaspi_name_core', ''),
            'size': row.get('size', ''),
            'sku_key': row.get('sku_key', ''),
            'sku_id': row.get('sku_id', ''),
            'reason': reason,
        })

    for item in missing:
        add_row({
            'store': item.store_name,
            'order_id': item.order_id,
            'kaspi_name_core': item.kaspi_name_core,
            'size': item.my_size,
            'sku_key': item.sku_key,
            'sku_id': item.sku_id,
            'reason': 'MISSING_PDF',
        })

    if extra_missing:
        for row in extra_missing:
            add_row(row)

    return rows


def write_package_summary(
    groups_by_store: dict[str, list[WaybillGroup]],
    output_path: Path,
    target_date: date,
):
    """Write package_summary.csv."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header with date
        writer.writerow(['Сегодня', target_date.strftime('%d.%m.%Y')])
        writer.writerow(['Магазин', 'Заказов', 'Мест'])

        total_orders = 0
        total_packages = 0

        # Store rows
        for store_name in sorted(groups_by_store.keys()):
            groups = groups_by_store[store_name]
            order_count = len(groups)
            package_count = count_packages(groups)

            writer.writerow([store_name, order_count, package_count])

            total_orders += order_count
            total_packages += package_count

        # Insert total at row 3 (after header)
        # We need to rewrite the file to insert total at correct position

    # Rewrite with total
    with open(output_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        f.write(lines[0])  # Date line
        f.write(lines[1])  # Header line
        f.write(f'Итого,{total_orders},{total_packages}\n')  # Total line
        for line in lines[2:]:  # Store lines
            f.write(line)


def main(
    crm_path: Path = None,
    db_path: Path = None,
    waybill_dir: Path = None,
    output_dir: Path = None,
    sheet_name: str = None,
    target_date: date = None,
    lookback_days: Optional[int] = 14,
    exact_date: bool = False,
    include_overdue: bool = False,
    output_layout: str = OUTPUT_LAYOUT_LEGACY,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Main waybill builder function.

    Returns dict with build statistics.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Set defaults
    crm_path = Path(crm_path) if crm_path else DEFAULT_CRM_PATH
    waybill_dir = Path(waybill_dir) if waybill_dir else DEFAULT_WAYBILL_DIR
    output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    sheet_name = sheet_name or DEFAULT_SHEET_NAME
    target_date = target_date or datetime.now(ALMATY_TZ).date()
    if include_overdue and exact_date:
        logger.warning("Both include_overdue and exact_date set; using include_overdue.")
        exact_date = False
    if output_layout not in {
        OUTPUT_LAYOUT_LEGACY,
        OUTPUT_LAYOUT_PER_STORE_AND_MERGED,
    }:
        raise ValueError(
            f"Unsupported output_layout={output_layout}. "
            f"Use {OUTPUT_LAYOUT_LEGACY} or {OUTPUT_LAYOUT_PER_STORE_AND_MERGED}."
        )
    if exact_date and not include_overdue:
        lookback_days = 0

    ensure_pdf_merger()

    if lookback_days is not None:
        min_date = target_date - timedelta(days=lookback_days)
        logger.info(
            f"Building waybills for {target_date} (date range {min_date} to {target_date})"
        )
    else:
        logger.info(f"Building waybills for {target_date} (date <= {target_date})")
    logger.info(f"Data root: {get_data_root()}")
    logger.info(f"CRM: {crm_path}")
    logger.info(f"Waybill dir: {waybill_dir}")
    logger.info(f"Output dir: {output_dir}")

    stats = {
        'orders_read': 0,
        'orders_grouped': 0,
        'orders_missing': 0,
        'stores_processed': 0,
        'total_packages': 0,
        'normal': 0,
        'multi_qty': 0,
        'multi_line': 0,
        'merged_groups': 0,
        'merged_packages': 0,
        'merged_normal': 0,
        'merged_multi_qty': 0,
        'merged_multi_line': 0,
        'delivery_groups': 0,
        'delivery_packages': 0,
        'delivery_normal': 0,
        'delivery_multi_qty': 0,
        'delivery_multi_line': 0,
        'whatsapp_groups': 0,
        'whatsapp_packages': 0,
        'whatsapp_normal': 0,
        'whatsapp_multi_qty': 0,
        'whatsapp_multi_line': 0,
    }

    # Read orders from the current CRM batch only.
    resolved_db_path = resolve_db_path(db_path)
    crm_df: Optional[pd.DataFrame] = None
    orders: list[OrderItem] = []
    db_orders: list[OrderItem] = []
    api_order_ids: set[str] = set()
    carryforward_orders_by_store: dict[str, set[str]] = {}
    carryforward_order_ids: set[str] = set()

    # Prefer Kaspi API planned date for selection (freshest)
    api_since_days = max(lookback_days if lookback_days is not None else 7, 7)
    api_orders_by_store: dict[str, set[str]] = {}
    api_error_stores: set[str] = set()
    selection_cache = load_selection_cache(
        waybill_dir, target_date, include_overdue=include_overdue, exact_date=exact_date
    )
    if selection_cache:
        api_orders_by_store = selection_cache
        api_order_ids = set().union(*api_orders_by_store.values())
        logger.info(
            f"Using cached API selection: {len(api_order_ids)} orders for {target_date}"
        )
    else:
        api_orders_by_store, api_error_stores = get_api_order_ids_for_date(
            target_date=target_date,
            since_days=api_since_days,
            verbose=verbose,
            include_overdue=include_overdue,
        )
        if api_error_stores:
            logger.warning(
                "API selection failed for stores: "
                + ", ".join(sorted(api_error_stores))
                + " — falling back to DB/CRM selection for all stores"
            )
            api_order_ids = set()
        elif api_orders_by_store:
            api_order_ids = set().union(*api_orders_by_store.values())
            logger.info(
                f"API selection: {len(api_order_ids)} orders for {target_date}"
            )

    if resolved_db_path:
        logger.info(f"DB: {resolved_db_path}")
        if include_overdue:
            carryforward_orders_by_store = get_overdue_waybill_ready_order_ids_from_db(
                resolved_db_path,
                target_date=target_date,
                lookback_days=lookback_days,
            )
            carryforward_order_ids = (
                set().union(*carryforward_orders_by_store.values())
                if carryforward_orders_by_store
                else set()
            )
            if carryforward_order_ids:
                logger.info(
                    f"Added {len(carryforward_order_ids)} overdue waybill-ready DB carry-forward orders"
                )

    if carryforward_order_ids:
        api_order_ids |= carryforward_order_ids

    if resolved_db_path:
        db_orders = read_db_orders(
            resolved_db_path,
            target_date,
            lookback_days=lookback_days,
            order_id_filter=api_order_ids if api_order_ids else None,
        )
        if db_orders:
            orders = enrich_orders_with_crm(
                db_orders,
                crm_path,
                sheet_name,
                target_date,
                lookback_days=lookback_days,
                apply_date_filter=not bool(api_order_ids),
                crm_df=crm_df,
            )
            logger.info("Using DB-first size decisions for order selection")

    if not orders:
        crm_df = load_crm_dataframe(crm_path, sheet_name)
        orders = read_crm_orders(
            crm_path,
            sheet_name,
            target_date,
            order_id_filter=api_order_ids if api_order_ids else None,
            historical_fallback_order_ids=carryforward_order_ids,
            lookback_days=lookback_days,
            apply_date_filter=not bool(api_order_ids),
            crm_df=crm_df,
        )
        if orders:
            logger.info("Using current-batch CRM manual sizes for order selection")
    stats['orders_read'] = len(orders)

    if not orders:
        logger.warning("No orders found with size decisions")
        return stats

    # Load waybills from folder (API downloads) and ZIP files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        target_order_ids = {o.order_id for o in orders if o.order_id}
        waybill_map = load_all_waybills(
            waybill_dir,
            temp_path,
            order_id_filter=target_order_ids,
        )

        # Group orders
        groups, missing = group_orders(orders, waybill_map)
        stats['orders_grouped'] = len(groups)
        stats['orders_missing'] = len(
            {item.order_id for item in missing if item.order_id and item.order_id != "0"}
        )

        # Missing diagnostics (DB-first workflows)
        missing_report_rows: list[dict] = []
        missing_crm_ids: set[str] = set()
        missing_size_ids: set[str] = set()
        if (db_orders or api_order_ids) and crm_df is not None:
            base_ids = api_order_ids or {o.order_id for o in db_orders}
            missing_crm_ids, missing_size_ids = get_crm_missing_info(
                crm_path,
                sheet_name,
                target_date,
                base_ids,
                lookback_days,
                crm_df=crm_df,
            )
            db_store_map = {o.order_id: o.store_name for o in db_orders}
            for oid in sorted(missing_crm_ids):
                missing_report_rows.append({
                    'store': db_store_map.get(oid, ''),
                    'order_id': oid,
                    'reason': 'CRM_MISSING_FOR_DATE',
                })
            for oid in sorted(missing_size_ids):
                missing_report_rows.append({
                    'store': db_store_map.get(oid, ''),
                    'order_id': oid,
                    'reason': 'NO_FINAL_SIZE',
                })
        elif db_orders or api_order_ids:
            logger.info(
                "Skipping CRM missing diagnostics; DB-first waybill build has no CRM workbook dependency."
            )
        missing_rows = collect_missing_rows(missing, missing_report_rows)

        # Group by store
        groups_by_store = defaultdict(list)
        for group in groups:
            groups_by_store[group.store_name].append(group)

        # Create output directory
        if not dry_run:
            reset_today_output_dir(output_dir, output_layout, target_date=target_date)

        per_store_root = output_dir
        merged_root: Optional[Path] = None
        if output_layout == OUTPUT_LAYOUT_PER_STORE_AND_MERGED:
            per_store_root = output_dir / "PER_STORE"
            merged_root = output_dir / "MERGED"

        # Date prefix for folders (DD.MM.YY)
        date_prefix = target_date.strftime("%d.%m.%y")

        output_sets: list[tuple[str, dict[str, list[WaybillGroup]]]] = []
        if include_overdue:
            today_groups, overdue_groups = split_groups_by_overdue(
                groups_by_store, target_date
            )
            if today_groups:
                output_sets.append(("TODAY", today_groups))
            if overdue_groups:
                output_sets.append(("OVERDUE", overdue_groups))
        else:
            output_sets.append(("", dict(groups_by_store)))
        has_partitioned_sets = len(output_sets) > 1

        # Build output for each store
        for label, store_groups_map in output_sets:
            base_dir = per_store_root / label if label else per_store_root
            if not dry_run and store_groups_map:
                base_dir.mkdir(parents=True, exist_ok=True)
            for store_name, store_groups in store_groups_map.items():
                logger.info(
                    f"Processing store: {store_name} ({len(store_groups)} groups)"
                )

                store_stats = build_store_output(
                    store_name, store_groups, base_dir, date_prefix, dry_run
                )

                stats['stores_processed'] += 1
                stats['total_packages'] += store_stats['packages']
                stats['normal'] += store_stats['normal']
                stats['multi_qty'] += store_stats['multi_qty']
                stats['multi_line'] += store_stats['multi_line']

            if merged_root and store_groups_map:
                merged_base_dir = merged_root / label if label else merged_root
                if not dry_run:
                    merged_base_dir.mkdir(parents=True, exist_ok=True)

                merged_groups = build_cross_store_groups(
                    list(chain.from_iterable(store_groups_map.values()))
                )
                if merged_groups:
                    logger.info(
                        f"Processing merged groups ({label or 'ALL'}) "
                        f"({len(merged_groups)} groups)"
                    )
                    merged_stats = build_store_output(
                        "MERGED",
                        merged_groups,
                        merged_base_dir,
                        date_prefix,
                        dry_run,
                    )
                    stats['merged_groups'] += len(merged_groups)
                    stats['merged_packages'] += int(merged_stats.get('packages', 0))
                    stats['merged_normal'] += int(merged_stats.get('normal', 0))
                    stats['merged_multi_qty'] += int(merged_stats.get('multi_qty', 0))
                    stats['merged_multi_line'] += int(merged_stats.get('multi_line', 0))

        if merged_root:
            send_base_dir = merged_root / WHATSAPP_SEND_ROOT_NAME
            if not dry_run:
                send_base_dir.mkdir(parents=True, exist_ok=True)

            send_groups = build_cross_store_groups(
                list(chain.from_iterable(groups_by_store.values()))
            )
            if send_groups:
                logger.info(
                    f"Processing delivery merged groups ({WHATSAPP_SEND_ROOT_NAME}) "
                    f"({len(send_groups)} groups)"
                )
                send_stats = build_store_output(
                    "MERGED",
                    send_groups,
                    send_base_dir,
                    date_prefix,
                    dry_run,
                    send_batch_order_labels=True,
                )
                if not dry_run:
                    manifest_path = write_send_batch_manifest(
                        batch_root=send_stats["batch_dir"],
                        today_root=output_dir,
                        groups=send_groups,
                        target_date=target_date,
                        expected_overdue_order_ids=carryforward_order_ids,
                    )
                    initialize_send_ledger(
                        send_stats["batch_dir"] / SEND_LEDGER_FILE,
                        json.loads(manifest_path.read_text(encoding="utf-8")),
                    )
                stats['delivery_groups'] = len(send_groups)
                stats['delivery_packages'] = int(send_stats.get('packages', 0))
                stats['delivery_normal'] = int(send_stats.get('normal', 0))
                stats['delivery_multi_qty'] = int(send_stats.get('multi_qty', 0))
                stats['delivery_multi_line'] = int(send_stats.get('multi_line', 0))
                stats['whatsapp_groups'] = stats['delivery_groups']
                stats['whatsapp_packages'] = stats['delivery_packages']
                stats['whatsapp_normal'] = stats['delivery_normal']
                stats['whatsapp_multi_qty'] = stats['delivery_multi_qty']
                stats['whatsapp_multi_line'] = stats['delivery_multi_line']

        # Write top-level files
        if not dry_run:
            write_build_log(groups, missing, output_dir / "build_log.csv")
            write_missing_orders(
                missing,
                output_dir / "missing_orders.csv",
                extra_missing=missing_report_rows,
                rows=missing_rows,
            )
            write_package_summary(groups_by_store, output_dir / "package_summary.csv", target_date)

    # Summary
    logger.info("=" * 50)
    logger.info("Build Summary:")
    logger.info(f"  Orders read: {stats['orders_read']}")
    logger.info(f"  Orders grouped: {stats['orders_grouped']}")
    logger.info(f"  Orders missing: {stats['orders_missing']}")
    logger.info(f"  Stores processed: {stats['stores_processed']}")
    logger.info(f"  Total packages: {stats['total_packages']}")
    logger.info(f"  NORMAL: {stats['normal']}")
    logger.info(f"  MULTI_QTY: {stats['multi_qty']}")
    logger.info(f"  MULTI_LINE: {stats['multi_line']}")
    if output_layout == OUTPUT_LAYOUT_PER_STORE_AND_MERGED:
        logger.info(f"  Merged bundles: {stats['merged_groups']}")
        logger.info(f"  Merged packages: {stats['merged_packages']}")
        logger.info(f"  Merged NORMAL: {stats['merged_normal']}")
        logger.info(f"  Merged MULTI_QTY: {stats['merged_multi_qty']}")
        logger.info(f"  Merged MULTI_LINE: {stats['merged_multi_line']}")
        logger.info(f"  Delivery merged bundles: {stats['delivery_groups']}")
        logger.info(f"  Delivery merged packages: {stats['delivery_packages']}")
        logger.info(f"  Delivery merged NORMAL: {stats['delivery_normal']}")
        logger.info(f"  Delivery merged MULTI_QTY: {stats['delivery_multi_qty']}")
        logger.info(f"  Delivery merged MULTI_LINE: {stats['delivery_multi_line']}")
    if missing_rows:
        logger.warning("Missing orders (first 5):")
        for row in missing_rows[:5]:
            logger.warning(
                f"  {row.get('order_id')} | {row.get('store', '')} | {row.get('reason', '')}"
            )
    logger.info("=" * 50)

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build daily waybill bundles"
    )
    parser.add_argument(
        "--crm-file",
        type=Path,
        default=None,
        help=f"Path to CRM Excel file (default: {DEFAULT_CRM_PATH})"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional DB path (defaults to DATA_DIR/db/app.db if present)"
    )
    parser.add_argument(
        "--waybill-dir",
        type=Path,
        default=None,
        help=f"Directory with waybill ZIP files (default: {DEFAULT_WAYBILL_DIR})"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--sheet",
        type=str,
        default=None,
        help=f"CRM sheet name (default: {DEFAULT_SHEET_NAME})"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date for filtering (YYYY-MM-DD format, default: today)"
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=14,
        help="Include orders with planned date within N days before target (default: 14)"
    )
    parser.add_argument(
        "--exact-date",
        action="store_true",
        help="Only include orders with planned date == target_date"
    )
    parser.add_argument(
        "--include-overdue",
        action="store_true",
        help="Include orders with planned date <= target_date (bounded by lookback)"
    )
    parser.add_argument(
        "--output-layout",
        choices=[OUTPUT_LAYOUT_LEGACY, OUTPUT_LAYOUT_PER_STORE_AND_MERGED],
        default=OUTPUT_LAYOUT_LEGACY,
        help=(
            "Output folder layout: "
            "'legacy' keeps current structure; "
            "'per-store-and-merged' writes per-store output to PER_STORE and "
            "adds cross-store merged output to MERGED."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't create output files, just show what would be built"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()
    if args.include_overdue and args.exact_date:
        logger.warning("Both --include-overdue and --exact-date set; using --include-overdue.")
        args.exact_date = False

    # Parse target date
    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    # Run builder
    stats = main(
        crm_path=args.crm_file,
        db_path=args.db_path,
        waybill_dir=args.waybill_dir,
        output_dir=args.output_dir,
        sheet_name=args.sheet,
        target_date=target_date,
        lookback_days=args.lookback_days,
        exact_date=args.exact_date,
        include_overdue=args.include_overdue,
        output_layout=args.output_layout,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
