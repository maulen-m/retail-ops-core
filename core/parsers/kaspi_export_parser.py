"""
Kaspi ActiveOrders Export Parser for Order Tracking (Phase 9.5).

Parses Kaspi Excel exports for the order management flow (fact_orders_kaspi).
Distinct from kaspi_parser.py which handles sales ingestion (fact_sales_raw).

Key differences from kaspi_parser.py:
- Filters for shipment-ready orders (status = "Ожидает передачи курьеру")
- Supports target_date filtering for planned shipment date
- Uses config-driven column mapping from kaspi_column_map.yaml
- Dedup key: (order_id, sku_id, store_code) - handles multi-line orders correctly

Usage:
    from core.parsers.kaspi_export_parser import parse_active_orders, filter_for_shipment

    orders = parse_active_orders(Path("ActiveOrders.xlsx"))
    ready_orders = filter_for_shipment(orders, target_date=date.today())
"""

import re
import yaml
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from core.product_truth.rombik_kid30_alias import apply_rombik_kid30_alias
from core.utils.sku_map import lookup_sku_from_offer


# Path to column mapping config
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "kaspi_column_map.yaml"
COMPACT_BUNDLE_ARTICLE_RE = re.compile(
    r"^((?:SUIT-\d{2}-(?:LS|TS|TK))|(?:LINE-\d{2}-(?:LS|TS)))"
    r"-(ST|TRM)-(S|M|L|XL|2XL|3XL|4XL)-(\d{2})$",
    re.IGNORECASE,
)


@dataclass
class ParseResult:
    """Result of parsing an ActiveOrders file."""
    orders: list[dict]
    total_rows: int
    parsed_rows: int
    skipped_rows: int
    errors: list[str] = field(default_factory=list)


def load_column_config() -> dict:
    """Load column mapping configuration from YAML."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Column config not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _get_column_name(config: dict, field_name: str, df_columns: list[str]) -> Optional[str]:
    """
    Get actual column name from config, checking aliases.

    Args:
        config: Loaded YAML config
        field_name: Field name (e.g., 'order_id', 'status')
        df_columns: Available columns in DataFrame

    Returns:
        Actual column name found in df, or None
    """
    # Try primary name from kaspi_export_columns
    primary = config.get('kaspi_export_columns', {}).get(field_name)
    if primary and primary in df_columns:
        return primary

    # Try aliases
    aliases = config.get('column_aliases', {}).get(field_name, [])
    for alias in aliases:
        if alias in df_columns:
            return alias

    return None


def _parse_date(value: Any, config: dict) -> Optional[str]:
    """
    Parse date value to ISO format string.

    Handles:
    - datetime objects
    - DD.MM.YYYY format (Kaspi default)
    - YYYY-MM-DD format
    - Excel serial numbers

    Args:
        value: Date value (various formats)
        config: Column config with date_parsing settings

    Returns:
        ISO date string (YYYY-MM-DD) or None
    """
    if pd.isna(value):
        return None

    date_config = config.get('date_parsing', {})
    dayfirst = date_config.get('dayfirst', True)

    # Already a datetime
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        return value.isoformat()

    # Try string parsing
    value_str = str(value).strip()

    # Try primary format first
    primary_fmt = date_config.get('primary_format', "%d.%m.%Y")
    try:
        return datetime.strptime(value_str, primary_fmt).strftime("%Y-%m-%d")
    except ValueError:
        pass

    # Try fallback formats
    for fmt in date_config.get('fallback_formats', []):
        try:
            return datetime.strptime(value_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try pandas parser with dayfirst
    try:
        parsed = pd.to_datetime(value, dayfirst=dayfirst)
        return parsed.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass

    # Handle Excel serial dates
    if date_config.get('handle_excel_serial', True):
        try:
            serial = float(value)
            if 40000 < serial < 50000:  # Reasonable Excel date range
                parsed = pd.to_datetime('1899-12-30') + pd.to_timedelta(serial, unit='D')
                return parsed.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    return None


def _normalize_store_code(store_value: Any, config: dict) -> str:
    """
    Normalize store name to standard store_code.

    Args:
        store_value: Raw store name from Kaspi
        config: Column config with store_code_map

    Returns:
        Normalized store code (e.g., 'PP1', 'UNIVERSAL')
    """
    if pd.isna(store_value):
        return config.get('store_code_map', {}).get('_default', 'UNKNOWN')

    store_str = str(store_value).strip()
    store_map = config.get('store_code_map', {})

    # Direct lookup
    if store_str in store_map:
        return store_map[store_str]

    # Case-insensitive lookup
    for key, code in store_map.items():
        if key.lower() == store_str.lower():
            return code

    return store_map.get('_default', store_str)


def _map_status_to_internal(kaspi_status: str, config: dict) -> str:
    """
    Map Kaspi Russian status to internal status code.

    Args:
        kaspi_status: Raw Kaspi status (Russian)
        config: Column config with status_filters

    Returns:
        Internal status code (NEW, READY, SHIPPED, etc.)
    """
    status_filters = config.get('status_filters', {})

    for _, status_info in status_filters.items():
        if status_info.get('russian') == kaspi_status:
            return status_info.get('internal', 'NEW')

    return 'NEW'


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value: Any, default: int = 1) -> int:
    """Safely convert value to int."""
    if pd.isna(value):
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _extract_size_from_article(article: str) -> Optional[str]:
    """
    Extract size from Kaspi article code.

    Common patterns:
    - ..._XL, ..._2XL (suffix after underscore)
    - ...XL, ...2XL (suffix without underscore)
    - Standalone size codes
    """
    if not article:
        return None

    article = str(article).upper().strip()

    # Size patterns in priority order
    patterns = [
        r'_([2-5]?X?[SML]|[2-5]XL)$',  # Suffix: _XL, _2XL
        r'\b([2-5]?XL)\b',              # 2XL, 3XL, etc.
        r'\b(XS|S|M|L)\b(?!.*[SML])',   # Single size (take first)
        r'[\s_](\d{2})$',               # Numeric size suffix: _48, _50
    ]

    for pattern in patterns:
        match = re.search(pattern, article)
        if match:
            return match.group(1)

    return None


def _looks_like_size_token(token: str) -> bool:
    """Heuristic for suffix tokens that encode size info in Артикул."""
    if not token:
        return False
    t = token.strip().strip("()")
    if not t:
        return False
    t_upper = t.upper()
    size_tokens = {"XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "ONE_SIZE", "ONESIZE", "OS"}
    if t_upper in size_tokens:
        return True
    if "/" in t_upper:
        if any(size in t_upper for size in size_tokens):
            return True
        if any(ch.isdigit() for ch in t_upper) and any(ch.isalpha() for ch in t_upper):
            return True
    if t_upper.isdigit() and len(t_upper) in (2, 3):
        return True
    if "-" in t_upper:
        parts = [p for p in t_upper.split("-") if p]
        if parts and all(p.isdigit() for p in parts):
            return True
    return False


def _strip_article_prefix(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    return re.sub(r"^[\d\s]+", "", text).strip()


def _extract_sku_parts(article: str, kaspi_name: str = None) -> dict:
    """
    Extract SKU components from article and/or kaspi name.

    Returns:
        Dict with: sku_key, sku_id, my_size (any can be None)
    """
    result = {'sku_key': None, 'sku_id': None, 'my_size': None}

    if not article:
        return result

    article_raw = _strip_article_prefix(article)
    article = article_raw.upper()

    compact_bundle_match = COMPACT_BUNDLE_ARTICLE_RE.match(article)
    if compact_bundle_match:
        sku_key = compact_bundle_match.group(1).upper()
        my_size = compact_bundle_match.group(3).upper()
        result['sku_key'] = sku_key
        result['my_size'] = my_size
        result['sku_id'] = f"{sku_key}_{my_size}"
        return result

    # Extract size first
    my_size = _extract_size_from_article(article)
    if not my_size and kaspi_name:
        my_size = _extract_size_from_article(kaspi_name)
    result['my_size'] = my_size

    # SKU_key is embedded at the beginning of Артикул
    raw_tokens = [t for t in article_raw.split("_") if t]
    upper_tokens = [t.upper() for t in raw_tokens]
    size_token = None
    while upper_tokens:
        token = upper_tokens[-1].strip()
        if not token:
            upper_tokens.pop()
            raw_tokens.pop()
            continue
        token_stripped = token.strip("()")
        if _looks_like_size_token(token_stripped):
            size_token = raw_tokens[-1]
            upper_tokens.pop()
            raw_tokens.pop()
            continue
        if token_stripped.isdigit() and len(token_stripped) >= 4:
            upper_tokens.pop()
            raw_tokens.pop()
            continue
        break

    if raw_tokens and len(raw_tokens) >= 2:
        result['sku_key'] = "_".join(raw_tokens)
        if not result.get('my_size') and size_token:
            result['my_size'] = size_token
        if result.get('my_size'):
            result['sku_id'] = f"{result['sku_key']}_{result['my_size']}"
        return result

    # Fallback: lookup by Kaspi_name_core mapping
    if kaspi_name:
        sku_key, map_size = lookup_sku_from_offer(kaspi_name)
        if sku_key:
            result['sku_key'] = sku_key
            if not result.get('my_size') and map_size:
                result['my_size'] = map_size
            if result.get('my_size'):
                result['sku_id'] = f"{result['sku_key']}_{result['my_size']}"
            return result

    # Check if article is already in our SKU format
    # Pattern: TYPE_LINE_GENDER_MODEL_COLOR or TYPE_LINE_GENDER_MODEL_COLOR_SIZE
    sku_pattern = r'^([A-Za-z0-9-]+_[A-Za-z0-9-]+_[A-Za-z0-9-]+_[A-Za-z0-9-]+_[A-Za-z0-9-]+)(?:_([A-Za-z0-9-]+))?$'
    match = re.match(sku_pattern, article_raw)

    if match:
        result['sku_key'] = match.group(1)
        if match.group(2):
            result['my_size'] = match.group(2)
            result['sku_id'] = article_raw
        elif my_size:
            result['sku_id'] = f"{result['sku_key']}_{my_size}"

    return result


def parse_active_orders_df(df: pd.DataFrame, source_file: str, config: dict = None) -> ParseResult:
    """
    Parse Kaspi ActiveOrders DataFrame (ActiveOrders.xlsx format).

    Args:
        df: DataFrame with ActiveOrders columns
        source_file: Source label for traceability
        config: Optional pre-loaded config (loads from yaml if None)

    Returns:
        ParseResult with list of order dicts with normalized column names
    """
    if config is None:
        config = load_column_config()

    df_columns = list(df.columns)
    total_rows = len(df)

    # Validate required columns
    required_fields = ['order_id', 'status', 'planned_date', 'product_name', 'article', 'price', 'store']
    missing = []
    column_map = {}

    for field in required_fields:
        col_name = _get_column_name(config, field, df_columns)
        if col_name:
            column_map[field] = col_name
        else:
            missing.append(field)

    if missing:
        expected = [config.get('kaspi_export_columns', {}).get(f, f) for f in missing]
        raise ValueError(
            f"Missing required columns: {expected}. "
            f"Available: {df_columns}"
        )

    # Get optional columns
    optional_fields = ['created_date', 'signature_required', 'quantity']
    for field in optional_fields:
        col_name = _get_column_name(config, field, df_columns)
        if col_name:
            column_map[field] = col_name

    # Parse each row
    orders = []
    errors = []
    skipped = 0

    for idx, row in df.iterrows():
        try:
            order = _parse_order_row(row, column_map, config, source_file)
            if order:
                orders.append(order)
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")
            skipped += 1

    return ParseResult(
        orders=orders,
        total_rows=total_rows,
        parsed_rows=len(orders),
        skipped_rows=skipped,
        errors=errors
    )


def parse_active_orders(filepath: Path, config: dict = None) -> ParseResult:
    """
    Parse Kaspi ActiveOrders*.xlsx export file.

    Args:
        filepath: Path to ActiveOrders Excel file
        config: Optional pre-loaded config (loads from yaml if None)

    Returns:
        ParseResult with list of order dicts with normalized column names
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    df = pd.read_excel(filepath)
    return parse_active_orders_df(df, source_file=filepath.name, config=config)


def _parse_order_row(
    row: pd.Series,
    column_map: dict,
    config: dict,
    source_file: str
) -> Optional[dict]:
    """Parse a single order row into normalized dict."""

    # Get order_id (required)
    order_id = row.get(column_map['order_id'])
    if pd.isna(order_id) or not str(order_id).strip():
        return None

    # Clean order_id
    order_id = str(order_id).strip()
    if order_id.endswith('.0'):
        order_id = order_id[:-2]

    # Get status
    kaspi_status = str(row.get(column_map['status'], '')).strip()
    internal_status = _map_status_to_internal(kaspi_status, config)

    # Get dates
    planned_date = _parse_date(row.get(column_map['planned_date']), config)
    created_date = _parse_date(
        row.get(column_map.get('created_date', 'created_date')),
        config
    ) if 'created_date' in column_map else None

    # Get product info
    kaspi_offer_name = str(row.get(column_map['product_name'], '')).strip()
    article = str(row.get(column_map['article'], '')).strip()

    # Extract SKU parts
    sku_parts = _extract_sku_parts(article, kaspi_offer_name)
    sku_parts.update(
        apply_rombik_kid30_alias(
            sku_key=sku_parts["sku_key"],
            sku_id=sku_parts["sku_id"],
            my_size=sku_parts["my_size"],
            event_at=created_date,
            kaspi_article=article,
            kaspi_offer_name=kaspi_offer_name,
        )
    )

    # Get store and normalize
    store_raw = row.get(column_map['store'])
    store_code = _normalize_store_code(store_raw, config)

    # Get numeric fields
    price = _safe_float(row.get(column_map['price']))
    quantity = _safe_int(row.get(column_map.get('quantity', 'quantity')), default=1)

    # Get signature requirement (for filtering)
    signature_col = column_map.get('signature_required')
    signature_required = None
    if signature_col:
        sig_val = str(row.get(signature_col, '')).strip()
        sig_filters = config.get('signature_filters', {})
        for sig_type, sig_info in sig_filters.items():
            if sig_info.get('russian') == sig_val:
                signature_required = not sig_info.get('include', True)
                break

    return {
        'order_id': order_id,
        'store_code': store_code,
        'channel_code': 'KSP',
        'kaspi_article': article if article else None,
        'kaspi_offer_name': kaspi_offer_name if kaspi_offer_name else None,
        'sku_key': sku_parts['sku_key'],
        'sku_id': sku_parts['sku_id'],
        'my_size': sku_parts['my_size'],
        'quantity': quantity,
        'unit_price_kzt': price,
        'created_at': created_date,
        'planned_shipment_date': planned_date,
        'kaspi_status': kaspi_status if kaspi_status else None,
        'internal_status': internal_status,
        'signature_required': signature_required,
        'source': 'EXCEL_EXPORT',
        'source_file': source_file,
    }


def filter_for_shipment(
    orders: list[dict],
    target_date: date = None,
    include_signature_required: bool = False
) -> list[dict]:
    """
    Filter orders ready for shipment.

    Conditions:
        - Status == "Ожидает передачи курьеру" (internal_status == READY)
        - Signature required == False (unless include_signature_required=True)
        - Planned date <= target_date (default: today)

    Args:
        orders: List of parsed order dicts
        target_date: Filter by planned_date <= this date (default: today)
        include_signature_required: If True, include orders requiring signature

    Returns:
        Filtered list of orders ready for shipment
    """
    if target_date is None:
        target_date = date.today()

    target_str = target_date.isoformat()

    filtered = []
    for order in orders:
        # Must be READY status
        if order.get('internal_status') != 'READY':
            continue

        # Check signature requirement
        if not include_signature_required and order.get('signature_required'):
            continue

        # Check planned date
        planned = order.get('planned_shipment_date')
        if planned and planned > target_str:
            continue

        filtered.append(order)

    return filtered


def normalize_order(raw: dict) -> dict:
    """
    Normalize raw Kaspi export row to Project 3 schema.

    This is mostly a pass-through since _parse_order_row already normalizes,
    but provided for API consistency.

    Returns:
        Dict ready for fact_orders_kaspi insertion
    """
    return {
        'order_id': raw.get('order_id'),
        'store_code': raw.get('store_code'),
        'channel_code': raw.get('channel_code', 'KSP'),
        'kaspi_article': raw.get('kaspi_article'),
        'kaspi_offer_name': raw.get('kaspi_offer_name'),
        'sku_key': raw.get('sku_key'),
        'sku_id': raw.get('sku_id'),
        'my_size': raw.get('my_size'),
        'quantity': raw.get('quantity', 1),
        'unit_price_kzt': raw.get('unit_price_kzt'),
        'created_at': raw.get('created_at'),
        'planned_shipment_date': raw.get('planned_shipment_date'),
        'kaspi_status': raw.get('kaspi_status'),
        'internal_status': raw.get('internal_status', 'NEW'),
        'source': raw.get('source', 'EXCEL_EXPORT'),
    }


def get_dedup_key(order: dict) -> tuple:
    """
    Get deduplication key for an order.

    Key: (order_id, sku_id, store_code)

    This correctly handles multi-line orders (same order_id, different SKUs).
    """
    return (
        order.get('order_id'),
        order.get('sku_id') or order.get('kaspi_offer_name'),  # Fallback if sku_id not extracted
        order.get('store_code')
    )


def deduplicate_orders(orders: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Deduplicate orders by (order_id, sku_id, store_code).

    Args:
        orders: List of order dicts

    Returns:
        Tuple of (unique_orders, duplicates)
    """
    seen = set()
    unique = []
    duplicates = []

    for order in orders:
        key = get_dedup_key(order)
        if key in seen:
            duplicates.append(order)
        else:
            seen.add(key)
            unique.append(order)

    return unique, duplicates


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python kaspi_export_parser.py <excel_file> [--filter-ready]")
        print("\nTests column config loading and parsing.")
        sys.exit(0)

    filepath = Path(sys.argv[1])
    filter_ready = '--filter-ready' in sys.argv

    print(f"Parsing: {filepath}")

    try:
        result = parse_active_orders(filepath)
        print(f"\nTotal rows: {result.total_rows}")
        print(f"Parsed: {result.parsed_rows}")
        print(f"Skipped: {result.skipped_rows}")

        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for err in result.errors[:5]:
                print(f"  - {err}")

        orders = result.orders

        if filter_ready:
            orders = filter_for_shipment(orders)
            print(f"\nReady for shipment: {len(orders)}")

        if orders:
            print("\nSample order:")
            for k, v in orders[0].items():
                print(f"  {k}: {v}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
