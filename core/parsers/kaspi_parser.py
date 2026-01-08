"""
Kaspi ActiveOrders Excel parser for Project 3.

Parses Kaspi's Russian-column Excel exports and maps to our DB schema.

Column Mapping (from Sales_Data_Model_V15.md):
    Russian (ActiveOrders)         →  DB Column (fact_sales_raw)
    --------------------------         -------------------------
    № заказа                       →  order_id
    Дата поступления заказа        →  order_date
    Название товара в Kaspi Магазине → kaspi_offer
    Артикул                        →  kaspi_article
    Сумма                          →  sell_price_kzt
    Количество                     →  quantity
    Стоимость доставки для продавца → delivery_fee_seller
    Стоимость доставки для покупателя → delivery_fee_buyer
    Статус                         →  order_status
"""

import re
from pathlib import Path
from typing import Optional
from datetime import datetime

import pandas as pd


# Russian column names from Kaspi ActiveOrders export
COLUMN_MAP_RUSSIAN = {
    "№ заказа": "order_id",
    "Дата поступления заказа": "order_date",
    "Название товара в Kaspi Магазине": "kaspi_offer",
    "Артикул": "kaspi_article",
    "Сумма": "sell_price_kzt",
    "Количество": "quantity",
    "Стоимость доставки для продавца": "delivery_fee_seller",
    "Стоимость доставки для покупателя": "delivery_fee_buyer",
    "Статус": "order_status",
}

# English column names (legacy/preprocessed files)
COLUMN_MAP_ENGLISH = {
    "OrderID": "order_id",
    "Date": "order_date",
    "KASPI_OFFER_NAME": "kaspi_offer",
    "Kaspi_article": "kaspi_article",
    "SKU_key": "sku_key",
    "SKU_ID": "sku_id",
    "MY_SIZE": "my_size",
    "Sell_price_kzt": "sell_price_kzt",
    "Quantity": "quantity",
    "Delivery_fee_kzt": "delivery_fee_seller",
    "Product_Type": "product_type",
    "Статус": "order_status",
}

# Required columns (either Russian OR English set)
REQUIRED_COLUMNS_RUSSIAN = [
    "№ заказа",
    "Дата поступления заказа",
    "Артикул",
    "Сумма",
    "Количество",
]

REQUIRED_COLUMNS_ENGLISH = [
    "OrderID",
    "Date",
    "Sell_price_kzt",
    "Quantity",
]

# Size mapping patterns (common Russian size formats → normalized)
SIZE_PATTERNS = {
    r"\b(XS|S|M|L|XL|2XL|3XL|4XL|5XL)\b": lambda m: m.group(1).upper(),
    r"\b(XXL)\b": lambda m: "2XL",
    r"\b(XXXL)\b": lambda m: "3XL",
    r"\bразмер[а-я]*\s*(\d+)\b": lambda m: m.group(1),  # размер 48 → 48
    r"\b(\d{2})\b(?![\d/])": lambda m: m.group(1),  # standalone 48, 50, etc.
}


def extract_sku_from_article(
    kaspi_article: str,
    kaspi_offer: Optional[str] = None
) -> dict[str, Optional[str]]:
    """
    Extract sku_key, sku_id, my_size from Kaspi article/offer.

    The Kaspi article often encodes:
    - Product type (CL, ELS, WB)
    - Model name (LINE52, LINE51)
    - Color
    - Size

    Format examples from legacy data:
    - SKU_key: CL_OC_MEN_LINE52_BLACK
    - SKU_ID: CL_OC_MEN_LINE52_BLACK_XL

    Args:
        kaspi_article: Kaspi article/SKU code
        kaspi_offer: Optional Kaspi listing name for additional context

    Returns:
        dict with keys: sku_key, sku_id, my_size (any can be None)
    """
    result = {
        "sku_key": None,
        "sku_id": None,
        "my_size": None,
        "product_type": None,
    }

    if not kaspi_article:
        return result

    article = str(kaspi_article).strip().upper()
    offer_text = str(kaspi_offer or "").upper()

    # Try to extract size from article or offer
    my_size = _extract_size(article) or _extract_size(offer_text)
    result["my_size"] = my_size

    # Try to detect product type from article patterns
    if "CL" in article or "КОМПЛЕКТ" in offer_text or "PRINT" in article:
        result["product_type"] = "CL"
    elif "ELS" in article or "ELASTIC" in article:
        result["product_type"] = "ELS"
    elif "WB" in article:
        result["product_type"] = "WB"
    elif "FUR" in article:
        result["product_type"] = "FUR"

    # If the article looks like our SKU format, use it directly
    sku_pattern = r"^([A-Z]+_[A-Z]+_[A-Z]+_[A-Z0-9]+_[A-Z]+)(?:_([A-Z0-9]+))?$"
    sku_match = re.match(sku_pattern, article)
    if sku_match:
        result["sku_key"] = sku_match.group(1)
        if sku_match.group(2):
            result["my_size"] = sku_match.group(2)
            result["sku_id"] = article
        elif my_size:
            result["sku_id"] = f"{result['sku_key']}_{my_size}"
        return result

    # For Kaspi articles that aren't our SKU format, try to infer from offer
    # This includes numeric articles (e.g., "102492502") and random alphanumeric
    if offer_text and not sku_match:
        # Try to extract model name and color from offer
        model = _extract_model_from_offer(offer_text)
        color = _extract_color_from_offer(offer_text)

        if model:
            # Build sku_key: Product_Type + Line + Gender + Model + Color
            gender = _detect_gender(offer_text)
            line = "OC"  # Default line, override if detectable
            ptype = result["product_type"] or "CL"

            parts = [ptype, line, gender, model]
            if color:
                parts.append(color)

            result["sku_key"] = "_".join(parts)

            if my_size:
                result["sku_id"] = f"{result['sku_key']}_{my_size}"

    return result


def _extract_size(text: str) -> Optional[str]:
    """Extract size from text using known patterns."""
    if not text:
        return None

    text = text.upper()

    # Try each size pattern
    for pattern, extractor in SIZE_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return extractor(match)

    return None


def _extract_model_from_offer(offer: str) -> Optional[str]:
    """Extract model name from Kaspi offer text."""
    offer = offer.upper()

    # Known model patterns from the business
    model_patterns = [
        r"\bPRINT[_\s]*5[В]?1\b",  # LINE52, Print5в1 (Russian в)
        r"\bPRINT[_\s]*(\d+[A-Z]*\d*)\b",  # LINE52, PRINT5v1
        r"\bLINE[_\s]*(\d+)\b",  # LINE51
        r"\bCOMBO[_\s]*(\d+)\b",  # COMBO01
        r"\bBASIC[_\s]*(\d+)\b",  # BASIC01
        r"\bELITE[_\s]*(\d+)\b",  # ELITE01
    ]

    for pattern in model_patterns:
        match = re.search(pattern, offer)
        if match:
            model_name = re.sub(r"[_\s]+", "", match.group(0))
            return model_name.upper()

    # Generic model: look for alphanumeric product codes
    generic = re.search(r"\b([A-Z]{2,}\d{2,})\b", offer)
    if generic:
        return generic.group(1)

    return None


def _extract_color_from_offer(offer: str) -> Optional[str]:
    """Extract color from Kaspi offer text."""
    offer = offer.upper()

    # Russian to English color mapping
    colors = {
        "ЧЕРНЫЙ": "BLACK",
        "ЧЁРНЫЙ": "BLACK",
        "ЧЕРН": "BLACK",
        "БЕЛЫЙ": "WHITE",
        "БЕЛ": "WHITE",
        "СЕРЫЙ": "GREY",
        "КРАСНЫЙ": "RED",
        "СИНИЙ": "BLUE",
        "ЗЕЛЕНЫЙ": "GREEN",
        "ЗЕЛЁНЫЙ": "GREEN",
        "ХАКИ": "KHAKI",
        "КАМО": "CAMO",
        "NAVY": "NAVY",
        "BLACK": "BLACK",
        "WHITE": "WHITE",
        "GREY": "GREY",
        "GRAY": "GREY",
    }

    for rus, eng in colors.items():
        if rus in offer:
            return eng

    return None


def _detect_gender(text: str) -> str:
    """Detect gender from text. Default: MEN."""
    text = text.upper()

    if any(w in text for w in ["ЖЕНСК", "WOMEN", "WOMAN", "ЖІНОЧ"]):
        return "WOMEN"
    if any(w in text for w in ["ДЕТСК", "KIDS", "CHILD", "ДИТЯЧ"]):
        return "KIDS"

    return "MEN"  # Default


def _normalize_columns(df: pd.DataFrame, validate: bool = True) -> pd.DataFrame:
    """Normalize ActiveOrders columns to internal names."""
    columns = list(df.columns)

    # Detect which column format we have (Russian or English)
    has_russian = any(col in columns for col in COLUMN_MAP_RUSSIAN)
    has_english = any(col in columns for col in COLUMN_MAP_ENGLISH)

    # Validate required columns
    if validate:
        if has_russian:
            missing = [c for c in REQUIRED_COLUMNS_RUSSIAN if c not in columns]
        elif has_english:
            missing = [c for c in REQUIRED_COLUMNS_ENGLISH if c not in columns]
        else:
            missing = REQUIRED_COLUMNS_RUSSIAN  # Default to Russian for error

        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Available: {columns}"
            )

    # Map columns to DB names (apply both maps, order matters)
    # English first (more specific), then Russian
    # Avoid duplicate target column names
    column_renames = {}
    target_names_used = set()

    for old, new in COLUMN_MAP_ENGLISH.items():
        if old in columns and new not in target_names_used:
            column_renames[old] = new
            target_names_used.add(new)

    for old, new in COLUMN_MAP_RUSSIAN.items():
        if old in columns and old not in column_renames and new not in target_names_used:
            column_renames[old] = new
            target_names_used.add(new)

    return df.rename(columns=column_renames)


def parse_active_orders_df(
    df: pd.DataFrame,
    store_code: str,
    source_file: str,
    validate: bool = True,
) -> list[dict]:
    """
    Parse Kaspi ActiveOrders DataFrame into list of dicts for DB insert.

    Args:
        df: DataFrame with ActiveOrders-style columns
        store_code: Store code (e.g., 'UNIVERSAL', 'ACMEWEAR')
        source_file: Source label for traceability
        validate: If True, raise on missing required columns

    Returns:
        List of dicts ready for fact_sales_raw insert.
    """
    df = _normalize_columns(df, validate=validate)

    records = []
    for _, row in df.iterrows():
        record = _process_row(row, store_code, source_file)
        if record:
            records.append(record)

    return records


def parse_active_orders(
    file_path: str | Path,
    store_code: str,
    validate: bool = True,
) -> list[dict]:
    """
    Parse Kaspi ActiveOrders Excel file into list of dicts for DB insert.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    df = pd.read_excel(path)
    return parse_active_orders_df(df, store_code=store_code, source_file=path.name, validate=validate)

    # Process each row
    records = []
    source_file = path.name

    for _, row in df.iterrows():
        record = _process_row(row, store_code, source_file)
        if record:
            records.append(record)

    return records


def _process_row(
    row: pd.Series,
    store_code: str,
    source_file: str
) -> Optional[dict]:
    """Process a single row into a DB-ready dict."""
    # Skip rows without order_id
    order_id = row.get("order_id")
    if pd.isna(order_id) or not str(order_id).strip():
        return None

    # Clean order_id: remove .0 suffix from floats, strip whitespace
    order_id = str(order_id).strip()
    if order_id.endswith(".0"):
        order_id = order_id[:-2]

    # Parse order date
    order_date = row.get("order_date")
    if pd.isna(order_date):
        order_date = None
    elif isinstance(order_date, datetime):
        order_date = order_date.strftime("%Y-%m-%d")
    else:
        # Try to parse string date with common formats
        date_str = str(order_date).strip()
        order_date = None
        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"]:
            try:
                order_date = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        # Fallback to pandas parser if standard formats fail
        if order_date is None:
            try:
                order_date = pd.to_datetime(date_str, dayfirst=True).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                order_date = None

    # Extract SKU info - prefer pre-existing columns from English format
    kaspi_article = row.get("kaspi_article")
    kaspi_article = str(kaspi_article).strip() if pd.notna(kaspi_article) else ""

    kaspi_offer = row.get("kaspi_offer")
    kaspi_offer = str(kaspi_offer).strip() if pd.notna(kaspi_offer) else ""

    # Check if we have pre-existing SKU columns (English format)
    existing_sku_key = row.get("sku_key")
    existing_sku_id = row.get("sku_id")
    existing_my_size = row.get("my_size")
    existing_product_type = row.get("product_type")

    # Use pre-existing values if available, otherwise extract from article
    if pd.notna(existing_sku_key) and str(existing_sku_key).strip():
        sku_key = str(existing_sku_key).strip()
        sku_id = str(existing_sku_id).strip() if pd.notna(existing_sku_id) else None
        my_size = str(existing_my_size).strip() if pd.notna(existing_my_size) else None
        product_type = str(existing_product_type).strip() if pd.notna(existing_product_type) else None
    else:
        sku_info = extract_sku_from_article(kaspi_article, kaspi_offer)
        sku_key = sku_info["sku_key"]
        sku_id = sku_info["sku_id"]
        my_size = sku_info["my_size"]
        product_type = sku_info["product_type"]

    # Get numeric values with defaults
    quantity = _safe_int(row.get("quantity"), default=1)
    sell_price = _safe_float(row.get("sell_price_kzt"), default=0.0)
    delivery_seller = _safe_float(row.get("delivery_fee_seller"), default=0.0)
    delivery_buyer = _safe_float(row.get("delivery_fee_buyer"), default=0.0)

    return {
        "order_id": str(order_id).strip(),
        "store_code": store_code,
        "order_date": order_date,
        "kaspi_offer": kaspi_offer if kaspi_offer else None,
        "kaspi_article": kaspi_article if kaspi_article else None,
        "sku_key": sku_key,
        "sku_id": sku_id,
        "my_size": my_size,
        "quantity": quantity,
        "sell_price_kzt": sell_price,
        "delivery_fee_seller": delivery_seller,
        "delivery_fee_buyer": delivery_buyer,
        "order_status": str(row.get("order_status", "")).strip() or None,
        "channel": "kaspi",
        "product_type": product_type,
        "source_file": source_file,
    }


def _safe_int(value, default: int = 0) -> int:
    """Safely convert value to int."""
    if pd.isna(value):
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


if __name__ == "__main__":
    # Quick test with sample data if available
    import sys

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        store = sys.argv[2] if len(sys.argv) > 2 else "UNIVERSAL"

        records = parse_active_orders(file_path, store)
        print(f"Parsed {len(records)} records from {file_path}")
        if records:
            print("\nFirst record:")
            for k, v in records[0].items():
                print(f"  {k}: {v}")
    else:
        print("Usage: python kaspi_parser.py <excel_file> [store_code]")
        print("\nTesting SKU extraction:")
        test_cases = [
            ("102492502", "Комплект ALPIKA 102492502 черный 48"),
            ("CL_OC_MEN_LINE52_BLACK_XL", None),
            ("12345", "Рашгард Line52 черный XL"),
        ]
        for article, offer in test_cases:
            result = extract_sku_from_article(article, offer)
            print(f"\nArticle: {article}")
            print(f"Offer: {offer}")
            print(f"Result: {result}")
