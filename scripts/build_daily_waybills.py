#!/usr/bin/env python3
"""
Build daily waybill bundles from CRM and waybill ZIPs.

Phase 11 TASK-192: Daily waybill grouping workflow.

Reads orders from SALES_KSP_CRM_V3.xlsx (with MY_SIZE filled), extracts waybill PDFs
from ZIP files, groups them by store/type, and creates organized output folders with manifests.

Usage:
    python scripts/build_daily_waybills.py
    python scripts/build_daily_waybills.py --date 2025-12-10
    python scripts/build_daily_waybills.py --lookback-days 14
    python scripts/build_daily_waybills.py --dry-run --verbose
"""

import argparse
import csv
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
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Optional

# Re-exec with venv python if available (ensures dependencies)
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if os.environ.get("VIRTUAL_ENV") is None and VENV_PYTHON.exists():
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

# Project root
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from core.db import DEFAULT_DB_PATH, get_db
from core.paths import data_path, get_data_root
from core.waybill.pdf_grouper import _extract_name_core as extract_name_core
from core.waybill.pdf_grouper import merge_pdfs
from core.integrations.kaspi_api_client import KaspiAPIClient, STORE_TOKEN_MAP, KaspiAuthError
from core.utils.kaspi_dates import planned_date_from_order

# Default paths
DEFAULT_CRM_PATH = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
DEFAULT_WAYBILL_DIR = data_path("excel_ui", "ActiveOrders")
DEFAULT_OUTPUT_DIR = data_path("excel_ui", "Kaspi_orders", "Today")
DEFAULT_SHEET_NAME = "SALES_KSP_CRM_1"

# Store code mapping (Kaspi warehouse codes -> display names)
STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
}

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
    '22': 1, '24': 2, '26': 3, '28': 4, '30': 5, '32': 6, '34': 7,
    # Men's letter sizes
    'S': 10, 'M': 11, 'L': 12, 'XL': 13, '2XL': 14, '3XL': 15, '4XL': 16,
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


def _planned_date_from_order(order: dict) -> Optional[date]:
    """Extract planned courier transmission date from API order."""
    return planned_date_from_order(order)


def get_api_order_ids_for_date(
    target_date: date,
    since_days: int = 7,
    store_filter: Optional[str] = None,
    verbose: bool = False,
) -> tuple[dict[str, set[str]], set[str]]:
    """Fetch KASPI_DELIVERY orders from API and return order IDs for target_date."""
    orders_by_store: dict[str, set[str]] = {}
    error_stores: set[str] = set()

    stores = list(STORE_TOKEN_MAP.keys())
    if store_filter:
        store_filter = store_filter.upper()
        if store_filter in STORE_TOKEN_MAP:
            stores = [store_filter]

    since = (datetime.now(ALMATY_TZ) - timedelta(days=since_days)).strftime('%Y-%m-%d')

    for store_code in stores:
        try:
            client = KaspiAPIClient(store_code=store_code)
            orders = client.list_all_orders(state='KASPI_DELIVERY', since=since)
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
            planned_date = _planned_date_from_order(order)
            if planned_date == target_date:
                order_code = order.get('attributes', {}).get('code', '')
                if order_code:
                    ids.add(order_code)

        if ids:
            orders_by_store[store_code] = ids
        if verbose:
            logger.info(f"{store_code}: {len(ids)} orders for {target_date}")

    return orders_by_store, error_stores


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


def _pick_size(assigned_size: Any, my_size: Any) -> str:
    """Prefer assigned_size from DB, fallback to my_size."""
    size = _coerce_str(assigned_size)
    if size and size.lower() not in ("nan", "none"):
        return size
    size = _coerce_str(my_size)
    if size and size.lower() not in ("nan", "none"):
        return size
    return ""


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
                planned_shipment_date
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

        rows = conn.execute(query, params).fetchall()

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

        kaspi_offer_name = _coerce_str(row["kaspi_offer_name"])
        sku_key = _coerce_str(row["sku_key"])
        sku_id = _coerce_str(row["sku_id"])

        kaspi_name_core = ""
        if kaspi_offer_name:
            kaspi_name_core = extract_name_core(kaspi_offer_name)
        if not kaspi_name_core or kaspi_name_core.lower() == "unknown":
            kaspi_name_core = sku_key or sku_id or "UNKNOWN"

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
    lookback_days: Optional[int] = None,
    apply_date_filter: bool = True,
) -> list[OrderItem]:
    """
    Read orders from CRM Excel file.

    Filters for orders where:
    - MY_SIZE is filled (not empty)
    - PLANNED_SHIPPING_DATE within [target_date - lookback_days, target_date] (if specified)

    Returns list of OrderItem objects.
    """
    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    logger.info(f"Reading CRM from {crm_path}")
    df = pd.read_excel(crm_path, sheet_name=sheet_name)

    orders = []
    skipped_no_size = 0
    skipped_date = 0
    skipped_no_date = 0
    skipped_not_target = 0

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
        kaspi_name_core = str(row.get('Kaspi_name_core', '')).strip()
        if not kaspi_name_core or kaspi_name_core.lower() == 'nan':
            kaspi_name_core = "UNKNOWN"

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
) -> list[OrderItem]:
    """Use CRM rows to enrich grouping fields (Kaspi_name_core, MY_SIZE, qty)."""
    if not db_orders:
        return []

    order_ids = {o.order_id for o in db_orders}
    crm_orders = read_crm_orders(
        crm_path,
        sheet_name,
        target_date,
        order_id_filter=order_ids,
        lookback_days=lookback_days,
        apply_date_filter=apply_date_filter,
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
) -> tuple[set[str], set[str]]:
    """
    Return (missing_in_crm, missing_size) for target_date.

    missing_in_crm: order_ids not present in CRM rows for target_date.
    missing_size: order_ids present in CRM rows for target_date but MY_SIZE empty.
    """
    if not crm_path.exists() or not order_ids:
        return set(order_ids), set()

    df = pd.read_excel(crm_path, sheet_name=sheet_name)
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


def load_waybills_from_folder(waybill_folder: Path) -> dict[str, Path]:
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
            waybill_map[order_id] = pdf_path
            continue

        # Try {order_id}.pdf pattern (downloaded via API)
        if basename.endswith('.pdf'):
            potential_order_id = basename[:-4]  # Remove .pdf
            if potential_order_id.isdigit():
                waybill_map[potential_order_id] = pdf_path

    logger.info(f"Loaded {len(waybill_map)} waybills from folder")
    return waybill_map


def extract_waybills_from_zips(
    zip_dir: Path,
    temp_dir: Path,
    pattern: str = "waybill*.zip"
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
) -> dict[str, Path]:
    """
    Load waybills from both folder (API downloads) and ZIP files.

    Priority: folder first, then ZIP extraction (folder takes precedence).

    Returns dict mapping order_id -> PDF path.
    """
    waybill_map = {}

    # 1. First, extract from ZIP files
    waybill_map.update(extract_waybills_from_zips(waybill_dir, temp_dir))

    # 2. Then, load from waybills folder (overrides ZIP if exists)
    waybill_folder = waybill_dir / waybill_folder_name
    folder_waybills = load_waybills_from_folder(waybill_folder)
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
        # Местовая-{N}_{core}_{size}-{qty}.pdf
        return f"Местовая-{index}_{name_core}_{size}-{group.total_quantity}.pdf"

    elif group.group_type == "MULTI_LINE":
        # Местовая-{N}_{core1}-{sz1}-{q1}(1-N)_{core2}-{sz2}-{q2}(2-N).pdf
        parts = []
        total = len(group.items)
        for i, item in enumerate(group.items, 1):
            core = sanitize_filename(item.kaspi_name_core)
            sz = sanitize_filename(item.my_size)
            parts.append(f"{core}-{sz}-{item.quantity}({i}-{total})")

        return f"Местовая-{index}_{'_'.join(parts)}.pdf"

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


def build_store_output(
    store_name: str,
    groups: list[WaybillGroup],
    base_output_dir: Path,
    date_prefix: str,
    dry_run: bool = False,
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
    store_dir = base_output_dir / folder_name

    stats = {
        'normal': 0,
        'multi_qty': 0,
        'multi_line': 0,
        'packages': count_packages(groups),
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create {store_dir}")
        return stats

    # Create directories
    normal_dir = store_dir / "NORMAL_singles"
    multi_line_dir = store_dir / "SPECIAL_multi_line"
    multi_qty_dir = store_dir / "SPECIAL_multi_qty"

    normal_dir.mkdir(parents=True, exist_ok=True)
    multi_line_dir.mkdir(parents=True, exist_ok=True)
    multi_qty_dir.mkdir(parents=True, exist_ok=True)

    # Group by type
    normal_groups = [g for g in groups if g.group_type == "NORMAL"]
    multi_qty_groups = [g for g in groups if g.group_type == "MULTI_QTY"]
    multi_line_groups = [g for g in groups if g.group_type == "MULTI_LINE"]

    # Sort each type
    normal_groups.sort(key=manifest_sort_key)
    multi_qty_groups.sort(key=manifest_sort_key)
    multi_line_groups.sort(key=manifest_sort_key)

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
            if len(pdf_paths) > 1:
                merge_pdfs(pdf_paths, output_path)
            else:
                if pdf_paths[0].exists():
                    shutil.copy2(pdf_paths[0], output_path)
            stats['normal'] += 1

    # Process MULTI_QTY
    for i, group in enumerate(multi_qty_groups, 1):
        filename = generate_filename(group, i)
        filename = ensure_unique(filename, group.order_id)
        output_path = multi_qty_dir / filename
        group.output_filename = f"SPECIAL_multi_qty/{filename}"

        pdf_paths = group.pdf_paths or ([group.pdf_path] if group.pdf_path else [])
        if pdf_paths:
            if len(pdf_paths) > 1:
                merge_pdfs(pdf_paths, output_path)
            else:
                if pdf_paths[0].exists():
                    shutil.copy2(pdf_paths[0], output_path)
            stats['multi_qty'] += 1

    # Process MULTI_LINE
    for i, group in enumerate(multi_line_groups, 1):
        filename = generate_filename(group, i)
        filename = ensure_unique(filename, group.order_id)
        output_path = multi_line_dir / filename
        group.output_filename = f"SPECIAL_multi_line/{filename}"

        pdf_paths = group.pdf_paths or ([group.pdf_path] if group.pdf_path else [])
        if pdf_paths:
            if len(pdf_paths) > 1:
                merge_pdfs(pdf_paths, output_path)
            else:
                if pdf_paths[0].exists():
                    shutil.copy2(pdf_paths[0], output_path)
            stats['multi_line'] += 1

    # Generate manifests
    write_manifest(normal_groups, store_dir / "manifest_normal_singles.csv", "NORMAL")
    write_manifest(multi_qty_groups, store_dir / "manifest_special_multi_qty.csv", "MULTI_QTY")
    write_manifest(multi_line_groups, store_dir / "manifest_special_multi_line.csv", "MULTI_LINE")

    return stats


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
                detail_parts = [
                    f"{sanitize_filename(item.kaspi_name_core)}-{item.my_size}-{item.quantity}"
                    for item in group.items
                ]
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
    if exact_date:
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
    }

    # Read orders (DB-first, CRM fallback)
    resolved_db_path = resolve_db_path(db_path)
    orders: list[OrderItem] = []
    api_order_ids: set[str] = set()

    # Prefer Kaspi API planned date for selection (freshest)
    api_since_days = max(lookback_days if lookback_days is not None else 7, 7)
    api_orders_by_store, api_error_stores = get_api_order_ids_for_date(
        target_date=target_date,
        since_days=api_since_days,
        verbose=verbose,
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
        db_orders = read_db_orders(
            resolved_db_path,
            target_date,
            lookback_days,
            order_id_filter=api_order_ids if api_order_ids else None,
        )
        orders = db_orders
        if orders:
            logger.info("Using DB for order selection")
            orders = enrich_orders_with_crm(
                orders,
                crm_path,
                sheet_name,
                target_date,
                lookback_days,
                apply_date_filter=not bool(api_order_ids),
            )
            # Add CRM-only orders missing in DB to avoid exclusions
            crm_all = read_crm_orders(
                crm_path,
                sheet_name,
                target_date,
                order_id_filter=api_order_ids if api_order_ids else None,
                lookback_days=lookback_days,
                apply_date_filter=not bool(api_order_ids),
            )
            if crm_all:
                existing_ids = {o.order_id for o in orders}
                extras = [o for o in crm_all if o.order_id not in existing_ids]
                if extras:
                    orders.extend(extras)
                    logger.info(
                        f"Added {len(extras)} CRM-only orders not in DB selection"
                    )
        else:
            logger.warning("No eligible orders found in DB; falling back to CRM")

    if not orders:
        orders = read_crm_orders(
            crm_path,
            sheet_name,
            target_date,
            order_id_filter=api_order_ids if api_order_ids else None,
            lookback_days=lookback_days,
            apply_date_filter=not bool(api_order_ids),
        )
    stats['orders_read'] = len(orders)

    if not orders:
        logger.warning("No orders found with size decisions")
        return stats

    # Load waybills from folder (API downloads) and ZIP files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        waybill_map = load_all_waybills(waybill_dir, temp_path)

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
        if db_orders or api_order_ids:
            base_ids = api_order_ids or {o.order_id for o in db_orders}
            missing_crm_ids, missing_size_ids = get_crm_missing_info(
                crm_path, sheet_name, target_date, base_ids, lookback_days
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
        missing_rows = collect_missing_rows(missing, missing_report_rows)

        # Group by store
        groups_by_store = defaultdict(list)
        for group in groups:
            groups_by_store[group.store_name].append(group)

        # Create output directory
        if not dry_run:
            # Clear existing Today directory
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        # Date prefix for folders (DD.MM.YY)
        date_prefix = target_date.strftime("%d.%m.%y")

        # Build output for each store
        for store_name, store_groups in groups_by_store.items():
            logger.info(f"Processing store: {store_name} ({len(store_groups)} groups)")

            store_stats = build_store_output(
                store_name, store_groups, output_dir, date_prefix, dry_run
            )

            stats['stores_processed'] += 1
            stats['total_packages'] += store_stats['packages']
            stats['normal'] += store_stats['normal']
            stats['multi_qty'] += store_stats['multi_qty']
            stats['multi_line'] += store_stats['multi_line']

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
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
