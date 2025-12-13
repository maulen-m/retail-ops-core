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
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    KaspiAuthError,
    KaspiWriteDisabledError,
    STORE_TOKEN_MAP,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default paths
DEFAULT_CRM_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
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
    skipped_date = 0
    skipped_store = 0

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

        # Filter by date - skip future orders
        if planned_date and planned_date > target_date:
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
            my_size=my_size,
            sku_key=sku_key,
            sku_id=sku_id,
            quantity=quantity,
            planned_date=planned_date,
        )
        orders_by_id[order_id].append(item)

    logger.info(f"Read {len(orders_by_id)} unique orders with MY_SIZE filled")
    logger.info(f"Skipped {skipped_no_size} rows without MY_SIZE")
    logger.info(f"Skipped {skipped_date} rows with future planned date")
    if store_filter:
        logger.info(f"Skipped {skipped_store} rows from other stores")

    return dict(orders_by_id)


def get_pending_assembly_orders() -> tuple[dict[str, set[str]], dict[str, str]]:
    """
    Get orders in "Упаковка" stage from ALL stores via API.

    Returns:
        - pending_by_store: dict store_api_code -> set of order_ids pending assembly
        - order_id_to_base64: dict order_code -> base64_id (for assemble_order_by_id)
    """
    pending_by_store: dict[str, set[str]] = {}
    order_id_to_base64: dict[str, str] = {}

    for store_code in STORE_TOKEN_MAP.keys():
        try:
            client = KaspiAPIClient(store_code=store_code)
            result = client.get_pending_assembly_orders()
            if result.success:
                orders = result.data.get('data', [])
                order_ids = set()
                for order in orders:
                    order_code = order.get('attributes', {}).get('code', '')
                    base64_id = order.get('id', '')
                    if order_code:
                        order_ids.add(order_code)
                        if base64_id:
                            order_id_to_base64[order_code] = base64_id
                pending_by_store[store_code] = order_ids
                logger.info(f"{store_code}: {len(order_ids)} orders pending assembly")
            else:
                logger.warning(f"{store_code}: Could not fetch pending orders: {result.error}")
                pending_by_store[store_code] = set()
        except KaspiAuthError as e:
            logger.warning(f"{store_code}: Auth error - {e}")
            pending_by_store[store_code] = set()

    return pending_by_store, order_id_to_base64


def ship_orders(
    orders_by_id: dict[str, list[OrderItem]],
    pending_orders: dict[str, set[str]],
    order_id_to_base64: dict[str, str],
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Ship orders via Kaspi API.

    For each order that is in pending_orders (Упаковка stage):
    1. Calculate package count
    2. Call assemble_order_by_id(base64_id, order_code, parcel_count)

    Args:
        orders_by_id: dict order_id -> list[OrderItem]
        pending_orders: dict store_api_code -> set of order_ids pending
        order_id_to_base64: dict order_code -> base64_id (from get_pending_assembly_orders)

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

            # Get Base64 ID from pre-fetched mapping
            base64_id = order_id_to_base64.get(order_id)
            if not base64_id:
                errors.append(f"{order_id}: No Base64 ID found (order may have changed state)")
                if verbose:
                    print(f"      -> SKIPPED: No Base64 ID (state changed?)")
                continue

            # Call API with pre-fetched Base64 ID (avoids re-fetch 404)
            try:
                result = client.assemble_order_by_id(base64_id, order_id, parcel_count=parcel_count)
                if result.success:
                    shipped += 1
                    if verbose:
                        print(f"      -> Shipped OK")
                else:
                    errors.append(f"{order_id}: API error - {result.error}")
                    if verbose:
                        print(f"      -> ERROR: {result.error}")
            except KaspiWriteDisabledError:
                logger.error("Write operations disabled. Set ENABLE_KASPI_WRITE=1 in .env")
                return {
                    'shipped': 0,
                    'skipped': len(orders_by_id),
                    'errors': ['Write operations disabled'],
                }
            except Exception as e:
                errors.append(f"{order_id}: {str(e)}")
                if verbose:
                    print(f"      -> EXCEPTION: {e}")

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
        '--dry-run',
        action='store_true',
        help='Preview only, do not call API'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Parse target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = date.today()

    print("=" * 60)
    print("  Kaspi Order Shipping (Set Package Count)")
    print("=" * 60)
    print(f"  CRM file: {args.crm_file}")
    print(f"  Target date: {target_date}")
    if args.store:
        print(f"  Store filter: {args.store}")
    if args.dry_run:
        print("  [DRY RUN MODE - No API calls]")
    print()

    # Step 1: Get pending assembly orders from API
    print("Step 1: Fetching pending assembly orders from API...")
    pending_orders, order_id_to_base64 = get_pending_assembly_orders()

    total_pending = sum(len(ids) for ids in pending_orders.values())
    if total_pending == 0:
        print("No orders pending assembly in Kaspi (Упаковка stage).")
        return

    print(f"  Found {total_pending} orders pending assembly across all stores")

    # Step 2: Read orders from CRM
    print("\nStep 2: Reading CRM for MY_SIZE data...")
    orders_by_id = read_crm_orders(
        args.crm_file,
        args.sheet,
        target_date,
        store_filter=args.store,
    )

    if not orders_by_id:
        print("No orders in CRM with MY_SIZE filled.")
        return

    print(f"  Found {len(orders_by_id)} orders in CRM with MY_SIZE")

    # Step 3: Ship orders
    print("\nStep 3: Shipping orders...")
    result = ship_orders(
        orders_by_id,
        pending_orders,
        order_id_to_base64,
        dry_run=args.dry_run,
        verbose=args.verbose,
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
