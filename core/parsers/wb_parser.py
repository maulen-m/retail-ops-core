"""
Wildberries sales data parser for Phase 8.

Parses WB sales reports exported from seller portal.
Maps WB columns to internal data model.

Column Mapping (from WB seller portal export):
    Russian (WB Export)              →  DB Column (fact_sales)
    ----------------------------        -------------------------
    Номер заказа                     →  order_id
    Дата заказа                      →  order_date
    Дата продажи                     →  sale_date
    Артикул продавца                 →  seller_sku
    Артикул WB                       →  wb_sku
    Баркод                           →  barcode
    Наименование                     →  product_name
    Размер                           →  size
    Цена розничная                   →  retail_price
    Цена со скидкой                  →  discounted_price
    Цена товара                      →  seller_price (commission base)
    Комиссия WB                      →  commission
    Логистика                        →  logistics_fee
    К перечислению                   →  payout
    Регион                           →  region
    Склад                            →  warehouse
    Тип                              →  order_type (Продажа/Возврат)
"""
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

import pandas as pd

# WB column mapping (Russian → Internal)
WB_COLUMN_MAP = {
    "Номер заказа": "order_id",
    "Дата заказа": "order_date",
    "Дата продажи": "sale_date",
    "Артикул продавца": "seller_sku",
    "Артикул WB": "wb_sku",
    "Баркод": "barcode",
    "Наименование": "product_name",
    "Размер": "size",
    "Цена розничная": "retail_price",
    "Цена со скидкой": "discounted_price",
    "Цена товара": "seller_price",  # Critical: commission base
    "Комиссия WB": "commission",
    "Логистика": "logistics_fee",
    "К перечислению": "payout",
    "Регион": "region",
    "Склад": "warehouse",
    "Тип": "order_type",  # Продажа, Возврат
}

# Required columns for validation
REQUIRED_COLUMNS = [
    "Номер заказа",
    "Дата заказа",
    "Артикул продавца",
    "Цена товара",
]

# Size normalization patterns
SIZE_MAP = {
    "XXL": "2XL",
    "XXXL": "3XL",
    "XXXXL": "4XL",
    "2ХL": "2XL",  # Cyrillic X
    "3ХL": "3XL",
    "4ХL": "4XL",
}


def parse_wb_sales(
    file_path: str | Path,
    store_code: str = "wb_fbo",
    validate: bool = True,
) -> list[dict]:
    """
    Parse WB sales report Excel file.

    Args:
        file_path: Path to WB sales export file
        store_code: Store code for this WB account
        validate: If True, raise on missing required columns

    Returns:
        List of dicts ready for DB insert

    Raises:
        ValueError: If required columns missing and validate=True
        FileNotFoundError: If file doesn't exist
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read Excel file
    df = pd.read_excel(path)
    columns = list(df.columns)

    # Validate required columns
    if validate:
        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise ValueError(
                f"Missing required WB columns: {missing}. "
                f"Available: {columns}"
            )

    # Rename columns
    column_renames = {
        old: new for old, new in WB_COLUMN_MAP.items() if old in columns
    }
    df = df.rename(columns=column_renames)

    # Process each row
    records = []
    source_file = path.name

    for _, row in df.iterrows():
        record = _process_wb_row(row, store_code, source_file)
        if record:
            records.append(record)

    return records


def _process_wb_row(
    row: pd.Series,
    store_code: str,
    source_file: str,
) -> Optional[dict]:
    """Process a single WB row into a DB-ready dict."""
    # Skip rows without order_id
    order_id = row.get("order_id")
    if pd.isna(order_id) or not str(order_id).strip():
        return None

    # Clean order_id
    order_id = str(order_id).strip()
    if order_id.endswith(".0"):
        order_id = order_id[:-2]

    # Parse dates
    order_date = _parse_wb_date(row.get("order_date"))
    sale_date = _parse_wb_date(row.get("sale_date"))

    # Get seller SKU and product name
    seller_sku = str(row.get("seller_sku", "")).strip()
    product_name = str(row.get("product_name", "")).strip()

    # Normalize size
    size = row.get("size")
    my_size = _normalize_wb_size(size) if pd.notna(size) else ""

    # Extract SKU info
    sku_key = _extract_sku_key_from_wb(seller_sku, product_name)
    sku_id = f"{sku_key}_{my_size}" if sku_key and my_size else sku_key

    # Get numeric values
    retail_price = _safe_float(row.get("retail_price"))
    discounted_price = _safe_float(row.get("discounted_price"))
    seller_price = _safe_float(row.get("seller_price"))
    commission = _safe_float(row.get("commission"))
    logistics_fee = _safe_float(row.get("logistics_fee"))
    payout = _safe_float(row.get("payout"))

    # Determine if return
    order_type = str(row.get("order_type", "")).strip()
    is_return = order_type.lower() in ["возврат", "return", "отмена"]

    return {
        "order_id": order_id,
        "order_date": order_date,
        "sale_date": sale_date or order_date,
        "channel_code": "WB",
        "store_code": store_code,
        "seller_sku": seller_sku,
        "wb_sku": str(row.get("wb_sku", "")).strip(),
        "barcode": str(row.get("barcode", "")).strip(),
        "product_name": product_name,
        "my_size": my_size,
        "sku_key": sku_key,
        "sku_id": sku_id,
        "retail_price_rub": retail_price,
        "discounted_price_rub": discounted_price,
        "seller_price_rub": seller_price,
        "commission_rub": commission,
        "logistics_fee_rub": logistics_fee,
        "payout_rub": payout,
        "region": str(row.get("region", "")).strip(),
        "warehouse": str(row.get("warehouse", "")).strip(),
        "order_type": order_type,
        "is_return": is_return,
        "quantity": -1 if is_return else 1,
        "source_file": source_file,
    }


def _parse_wb_date(value) -> Optional[str]:
    """Parse WB date format to ISO string."""
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        value = value.strip()
        # Try common WB date formats
        for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(value[:10], fmt[:len(fmt.split()[0])]).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Try pandas parser as fallback
        try:
            return pd.to_datetime(value, dayfirst=True).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    return None


def _normalize_wb_size(size) -> str:
    """Normalize WB size to internal format."""
    if pd.isna(size):
        return ""

    size = str(size).upper().strip()

    # Handle numeric sizes like "50" or "48-50"
    if re.match(r"^\d{2}(-\d{2})?$", size):
        return size

    # Map common variations
    return SIZE_MAP.get(size, size)


def _extract_sku_key_from_wb(seller_sku: str, product_name: str) -> str:
    """
    Extract internal sku_key from WB seller SKU.

    Assumes seller_sku follows pattern: SKU_KEY_SIZE
    e.g., 'CL_OC_MEN_LINE52_BLACK_XL' → 'CL_OC_MEN_LINE52_BLACK'

    Also tries to infer from product_name if seller_sku is not informative.
    """
    if not seller_sku:
        return ""

    seller_sku = seller_sku.upper().strip()

    # Common size suffixes to strip
    size_pattern = r"_(?:S|M|L|XL|2XL|3XL|4XL|XXL|XXXL|XXXXL|\d{2,3})$"

    # Check if seller_sku looks like our SKU format (has underscores and looks structured)
    if re.match(r"^[A-Z]+(_[A-Z0-9]+)+$", seller_sku):
        sku_key = re.sub(size_pattern, "", seller_sku, flags=re.IGNORECASE)
        return sku_key.upper()

    # If seller_sku is numeric or doesn't follow pattern, try to infer from product_name
    if product_name:
        product_name = product_name.upper()

        # Try to detect model from product name
        model = None
        if "PRINT" in product_name:
            match = re.search(r"PRINT\s*(\d+)", product_name)
            model = f"PRINT{match.group(1)}" if match else "LINE52"
        elif "LINE" in product_name:
            match = re.search(r"LINE\s*(\d+)", product_name)
            model = f"LINE{match.group(1)}" if match else "LINE51"

        if model:
            # Try to detect color
            colors = {
                "ЧЕРН": "BLACK", "ЧЁРН": "BLACK", "BLACK": "BLACK",
                "БЕЛ": "WHITE", "WHITE": "WHITE",
                "СЕР": "GREY", "GREY": "GREY", "GRAY": "GREY",
                "ХАКИ": "KHAKI", "NAVY": "NAVY",
            }
            color = None
            for rus, eng in colors.items():
                if rus in product_name:
                    color = eng
                    break

            # Build sku_key
            parts = ["CL", "OC", "MEN", model]
            if color:
                parts.append(color)
            return "_".join(parts)

    # Fallback: use seller_sku as-is
    return seller_sku


def validate_wb_record(record: dict) -> tuple[bool, Optional[str]]:
    """
    Validate a WB sales record before insert.

    Returns: (is_valid, error_message)
    """
    if not record.get("order_id"):
        return False, "Missing order_id"

    if not record.get("sku_key"):
        return False, "Could not extract sku_key"

    if record.get("seller_price_rub", 0) <= 0 and not record.get("is_return"):
        return False, "Invalid seller_price_rub for non-return order"

    return True, None


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


if __name__ == "__main__":
    import sys

    print("WB Parser Module")
    print("=" * 60)

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        store = sys.argv[2] if len(sys.argv) > 2 else "wb_fbo"

        records = parse_wb_sales(file_path, store)
        print(f"Parsed {len(records)} records from {file_path}")
        if records:
            print("\nFirst record:")
            for k, v in records[0].items():
                print(f"  {k}: {v}")
    else:
        print("Usage: python wb_parser.py <excel_file> [store_code]")
        print("\nTesting SKU extraction:")

        test_cases = [
            ("CL_OC_MEN_LINE52_BLACK_XL", "Комплект Line52 черный"),
            ("12345678", "Рашгард Line52 черный XL"),
            ("LINE51_BLACK_M", "Леггинсы Line51"),
        ]

        for sku, name in test_cases:
            result = _extract_sku_key_from_wb(sku, name)
            print(f"\n  Seller SKU: {sku}")
            print(f"  Product:    {name}")
            print(f"  SKU Key:    {result}")
