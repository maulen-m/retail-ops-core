#!/usr/bin/env python3
"""
Build daily waybill bundles from CRM and waybill ZIPs.

Phase 11 TASK-192: Daily waybill grouping workflow.

Reads orders from SALES_KSP_CRM_V3.xlsx (with MY_SIZE filled), extracts waybill PDFs
from ZIP files, groups them by store/type, and creates organized output folders with manifests.

Usage:
    python scripts/build_daily_waybills.py
    python scripts/build_daily_waybills.py --date 2025-12-10
    python scripts/build_daily_waybills.py --dry-run --verbose
"""

import argparse
import csv
import logging
import re
import shutil
import sys
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path, get_data_root

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
    output_filename: str = ""

    @property
    def order_id(self) -> str:
        return self.items[0].order_id if self.items else ""

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


def read_crm_orders(
    crm_path: Path,
    sheet_name: str,
    target_date: date = None,
) -> list[OrderItem]:
    """
    Read orders from CRM Excel file.

    Filters for orders where:
    - MY_SIZE is filled (not empty)
    - PLANNED_SHIPPING_DATE <= target_date (if specified)

    Returns list of OrderItem objects.
    """
    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    logger.info(f"Reading CRM from {crm_path}")
    df = pd.read_excel(crm_path, sheet_name=sheet_name)

    orders = []
    skipped_no_size = 0
    skipped_date = 0

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

        # Filter by date - Phase 12 Part 6: exact match (was > which allowed all past dates)
        if target_date and planned_date and planned_date != target_date:
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
    logger.info(f"Skipped {skipped_date} orders with future planned date")

    return orders


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

    # Process each order_id
    for order_id, items in by_order_id.items():
        # Check if waybill exists
        pdf_path = waybill_map.get(order_id)
        if not pdf_path:
            missing.extend(items)
            continue

        store_name = items[0].store_name

        # MULTI_LINE: Same order_id, multiple different products
        if len(items) > 1:
            group = WaybillGroup(
                group_type="MULTI_LINE",
                store_name=store_name,
                items=items,
                pdf_path=pdf_path,
            )
            groups.append(group)
            continue

        item = items[0]

        # MULTI_QTY: Single product with quantity > 1
        if item.quantity > 1:
            group = WaybillGroup(
                group_type="MULTI_QTY",
                store_name=store_name,
                items=[item],
                pdf_path=pdf_path,
            )
            groups.append(group)
            continue

        # NORMAL: Single product, quantity = 1
        group = WaybillGroup(
            group_type="NORMAL",
            store_name=store_name,
            items=[item],
            pdf_path=pdf_path,
        )
        groups.append(group)

    logger.info(f"Grouped into {len(groups)} bundles, {len(missing)} missing waybills")
    return groups, missing


def generate_filename(group: WaybillGroup, index: int) -> str:
    """Generate output filename based on group type."""
    name_core = sanitize_filename(group.kaspi_name_core)
    size = sanitize_filename(group.my_size)

    if group.group_type == "NORMAL":
        # {kaspi_name_core}_{MY_SIZE}-{QTY}.pdf
        return f"{name_core}_{size}-{group.total_quantity}.pdf"

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

    # Process NORMAL
    for group in normal_groups:
        filename = generate_filename(group, 0)
        output_path = normal_dir / filename
        group.output_filename = f"NORMAL_singles/{filename}"

        if group.pdf_path and group.pdf_path.exists():
            shutil.copy2(group.pdf_path, output_path)
            stats['normal'] += 1

    # Process MULTI_QTY
    for i, group in enumerate(multi_qty_groups, 1):
        filename = generate_filename(group, i)
        output_path = multi_qty_dir / filename
        group.output_filename = f"SPECIAL_multi_qty/{filename}"

        if group.pdf_path and group.pdf_path.exists():
            shutil.copy2(group.pdf_path, output_path)
            stats['multi_qty'] += 1

    # Process MULTI_LINE
    for i, group in enumerate(multi_line_groups, 1):
        filename = generate_filename(group, i)
        output_path = multi_line_dir / filename
        group.output_filename = f"SPECIAL_multi_line/{filename}"

        if group.pdf_path and group.pdf_path.exists():
            shutil.copy2(group.pdf_path, output_path)
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
                'order_id': group.order_id,
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
                'order_id': group.order_id,
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


def write_missing_orders(missing: list[OrderItem], output_path: Path):
    """Write missing_orders.csv."""
    if not missing:
        return

    fieldnames = ['store', 'order_id', 'kaspi_name_core', 'size', 'sku_key', 'sku_id', 'reason']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for item in missing:
            writer.writerow({
                'store': item.store_name,
                'order_id': item.order_id,
                'kaspi_name_core': item.kaspi_name_core,
                'size': item.my_size,
                'sku_key': item.sku_key,
                'sku_id': item.sku_id,
                'reason': 'PDF_NOT_FOUND',
            })


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
    waybill_dir: Path = None,
    output_dir: Path = None,
    sheet_name: str = None,
    target_date: date = None,
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
    target_date = target_date or date.today()

    logger.info(f"Building waybills for {target_date}")
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

    # Read CRM orders
    orders = read_crm_orders(crm_path, sheet_name, target_date)
    stats['orders_read'] = len(orders)

    if not orders:
        logger.warning("No orders found with MY_SIZE filled")
        return stats

    # Load waybills from folder (API downloads) and ZIP files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        waybill_map = load_all_waybills(waybill_dir, temp_path)

        # Group orders
        groups, missing = group_orders(orders, waybill_map)
        stats['orders_grouped'] = len(groups)
        stats['orders_missing'] = len(missing)

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
            write_missing_orders(missing, output_dir / "missing_orders.csv")
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
        waybill_dir=args.waybill_dir,
        output_dir=args.output_dir,
        sheet_name=args.sheet,
        target_date=target_date,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
