"""
TASK-176: Sales Ingestion Module (Phase 10)

Parses sales Excel files and ingests to sales_fact_v2 and stock_ledger.

Key constraint: Unique key is (order_id, store_code, kaspi_offer_name, sku_key, my_size)
- Same order can have same kaspi_offer_name with qty=2 but different sizes
- Same order can have different kaspi_offer_name with same sku_id
- sku_id is resolved from (sku_key, my_size) when possible to avoid false dedup

Tables used:
- sales_fact_v2: Enhanced sales with return tracking
- stock_ledger: Event-sourced stock changes (SALE/RETURN events)
- dim_sku_size: Size definitions for a SKU
"""

import sqlite3
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event, log_audit, inventory_pool_store_code
from core.calc.economics import calc_cogs, calc_delivery_fee, calc_net_rev
from core.product_truth.rombik_kid30_alias import apply_rombik_kid30_alias
from core.utils.sku_normalize import (
    VALID_SIZES,
    infer_size_from_sku_id,
    normalize_sku_key,
    normalize_size,
)

_SIZE_TOKEN_RE = re.compile(r"[A-Z0-9]+")


@dataclass(frozen=True)
class SalesIdentityResolution:
    sku_key: str | None
    sku_id: str | None
    my_size: str | None
    offer_name_mapping_hit: bool = False
    offer_name_mapping_sku_key_only: bool = False


def infer_size_from_offer_name(
    offer_name: str | None,
    synonyms: dict[str, str] | None = None,
    product_type: str | None = None,
) -> str | None:
    """Infer size token from a Kaspi offer name string."""
    if not offer_name:
        return None
    tokens = _SIZE_TOKEN_RE.findall(str(offer_name).upper())
    for token in tokens:
        candidate = normalize_size(token, product_type=product_type, synonyms=synonyms)
        if candidate and candidate in VALID_SIZES:
            return candidate
    return None


# Store code normalization map
STORE_CODE_MAP = {
    "universal": "UNIVERSAL",
    "acmewear": "ACMEWEAR",
    "store-d": "11KZ",
    "11_kz": "11KZ",
    "store_b": "STOREB",
    "samson": "SAMSON",
    "abyx": "ABYX",
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _clean_identity_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _is_placeholder_sku_key(value: str | None) -> bool:
    text = _clean_identity_value(value)
    return not text or text.upper() in {"CL", "UNKNOWN"}


def _sku_key_exists(conn: sqlite3.Connection, sku_key: str | None) -> bool:
    key = _clean_identity_value(sku_key)
    if not key or not _table_exists(conn, "dim_sku"):
        return False
    row = conn.execute(
        "SELECT 1 FROM dim_sku WHERE UPPER(TRIM(sku_key)) = UPPER(TRIM(?)) LIMIT 1",
        (key,),
    ).fetchone()
    return row is not None


def _lookup_offer_name_identity(
    conn: sqlite3.Connection,
    *,
    offer_name: str | None,
    store_code: str | None,
) -> tuple[str, str | None, str | None] | None:
    offer = _clean_identity_value(offer_name)
    store = _clean_identity_value(store_code)
    if not offer or not store or not _table_exists(conn, "dim_offer_name_identity"):
        return None

    row = conn.execute(
        """
        SELECT sku_key, sku_id, my_size
        FROM dim_offer_name_identity
        WHERE TRIM(offer_name) = TRIM(?)
          AND UPPER(TRIM(store_code)) = UPPER(TRIM(?))
        LIMIT 1
        """,
        (offer, store),
    ).fetchone()
    if not row:
        return None
    mapped_key = _clean_identity_value(row["sku_key"])
    if not mapped_key:
        return None
    return (
        mapped_key,
        _clean_identity_value(row["sku_id"]),
        _clean_identity_value(row["my_size"]),
    )


def _load_size_synonyms(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "dim_size_synonyms"):
        return {}
    rows = conn.execute(
        "SELECT alias, canonical_size FROM dim_size_synonyms"
    ).fetchall()
    synonyms: dict[str, str] = {}
    for alias, canonical in rows:
        if not alias or not canonical:
            continue
        key = str(alias).upper().replace(" ", "").replace("-", "")
        synonyms[key] = str(canonical).strip()
    return synonyms


def normalize_store_code(store_name: str) -> str:
    """Normalize store name to store code."""
    if not store_name or pd.isna(store_name):
        return "UNIVERSAL"

    clean = str(store_name).lower().strip().replace(" ", "_").replace("-", "_")
    return STORE_CODE_MAP.get(clean, store_name.upper())


def build_sales_dedupe_key(
    order_id: str,
    store_code: str,
    kaspi_offer_name: str,
    sku_key: str | None,
    my_size: str | None,
) -> tuple:
    """Return the canonical dedupe key for sales records."""
    return (
        str(order_id or ""),
        str(store_code or ""),
        str(kaspi_offer_name or ""),
        str(sku_key or ""),
        str(my_size or ""),
    )


def resolve_sales_identity_detail(
    conn: sqlite3.Connection,
    sku_id: str | None,
    sku_key: str | None,
    my_size: str | None,
    kaspi_offer_name: str | None = None,
    store_code: str | None = None,
) -> SalesIdentityResolution:
    """Resolve sku_key/sku_id/my_size from dim_sku_size and offer-name overrides."""
    return _resolve_sales_identity_detail(
        conn,
        sku_id,
        sku_key,
        my_size,
        kaspi_offer_name=kaspi_offer_name,
        store_code=store_code,
    )


def _resolve_sales_identity_detail(
    conn: sqlite3.Connection,
    sku_id: str | None,
    sku_key: str | None,
    my_size: str | None,
    kaspi_offer_name: str | None = None,
    store_code: str | None = None,
) -> SalesIdentityResolution:
    """Resolve sku_key/sku_id/my_size from dim_sku_size and offer-name overrides."""
    sku_id = str(sku_id).strip() if sku_id else None
    sku_key = str(sku_key).strip() if sku_key else None
    my_size = str(my_size).strip() if my_size else None
    synonyms = _load_size_synonyms(conn)
    product_type = None
    if sku_key and "_" in sku_key:
        product_type = sku_key.split("_", 1)[0]
    my_size = normalize_size(my_size, product_type=product_type, synonyms=synonyms)

    if sku_id:
        row = conn.execute(
            "SELECT sku_key, my_size FROM dim_sku_size WHERE sku_id = ?",
            (sku_id,),
        ).fetchone()
        if row:
            sku_key = row["sku_key"]
            product_type = sku_key.split("_", 1)[0] if sku_key and "_" in sku_key else product_type
            my_size = normalize_size(row["my_size"], product_type=product_type, synonyms=synonyms)
        else:
            # Attempt to normalize sku_id suffix (handles stray spaces like "_ XL")
            if "_" in sku_id:
                base, suffix = sku_id.rsplit("_", 1)
                candidate_product_type = base.split("_", 1)[0] if "_" in base else product_type
                candidate_size = normalize_size(
                    suffix,
                    product_type=candidate_product_type,
                    synonyms=synonyms,
                )
                candidate_key = normalize_sku_key(base)
                if candidate_key and candidate_size:
                    row2 = conn.execute(
                        "SELECT sku_id FROM dim_sku_size WHERE sku_key = ? AND my_size = ?",
                        (candidate_key, candidate_size),
                    ).fetchone()
                    if row2:
                        sku_id = row2["sku_id"]
                        sku_key = candidate_key
                        my_size = candidate_size

    if sku_key:
        sku_key = normalize_sku_key(sku_key)
        if "_" in sku_key:
            product_type = sku_key.split("_", 1)[0]

    if not my_size and sku_id:
        inferred_from_sku = infer_size_from_sku_id(sku_id)
        if inferred_from_sku:
            my_size = normalize_size(
                inferred_from_sku,
                product_type=product_type,
                synonyms=synonyms,
            )

    if not my_size and kaspi_offer_name and sku_key and sku_key.startswith("CL_"):
        inferred = infer_size_from_offer_name(
            kaspi_offer_name,
            synonyms=synonyms,
            product_type=product_type,
        )
        if inferred:
            my_size = inferred

    if sku_key and my_size:
        row = conn.execute(
            "SELECT sku_id FROM dim_sku_size WHERE sku_key = ? AND my_size = ?",
            (sku_key, my_size),
        ).fetchone()
        if row:
            sku_id = row["sku_id"]

    mapping = None
    if store_code and (not _sku_key_exists(conn, sku_key) or _is_placeholder_sku_key(sku_key)):
        mapping = _lookup_offer_name_identity(
            conn,
            offer_name=kaspi_offer_name,
            store_code=store_code,
        )
    if mapping:
        mapped_key, mapped_id, mapped_size = mapping
        if mapped_id and mapped_size:
            return SalesIdentityResolution(
                mapped_key,
                mapped_id,
                mapped_size,
                offer_name_mapping_hit=True,
                offer_name_mapping_sku_key_only=False,
            )
        return SalesIdentityResolution(
            mapped_key,
            sku_id,
            my_size,
            offer_name_mapping_hit=True,
            offer_name_mapping_sku_key_only=True,
        )

    return SalesIdentityResolution(sku_key, sku_id, my_size)


def resolve_sales_identity(
    conn: sqlite3.Connection,
    sku_id: str | None,
    sku_key: str | None,
    my_size: str | None,
    kaspi_offer_name: str | None = None,
    store_code: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Resolve sku_key/sku_id/my_size from dim_sku_size when possible."""
    resolved = _resolve_sales_identity_detail(
        conn,
        sku_id,
        sku_key,
        my_size,
        kaspi_offer_name=kaspi_offer_name,
        store_code=store_code,
    )
    return resolved.sku_key, resolved.sku_id, resolved.my_size


def parse_sales_excel(
    xlsx_path: str,
    sheet_name: str = "SALES_KSP_CRM_1",
) -> list[dict]:
    """
    Parse sales Excel file.

    Expected columns:
    - OrderID / № заказа: Order ID
    - Date / Дата поступления заказа: Order date
    - KASPI_OFFER_NAME / Название товара в Kaspi Магазине: Kaspi listing name
    - SKU_ID: Size-level SKU (derived from kaspi_offer_name via Sku_Map)
    - SKU_key: Style-level SKU
    - MY_SIZE: Size label
    - Quantity / Количество: Quantity
    - Sell_price_kzt / Сумма: Sell price
    - STORE_NAME: Store name
    - Return: Return flag (0/1)
    - Total_net_rev: Net revenue (if available)
    - Delivery_fee_kzt: Delivery fee (legacy export)
    - Стоимость доставки для продавца: Seller delivery fee
    - Стоимость доставки для покупателя: Buyer delivery fee

    Args:
        xlsx_path: Path to Excel file
        sheet_name: Sheet name (default: SALES_KSP_CRM_1)

    Returns:
        List of sale dicts
    """
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)

    # Column name normalization (handle both English and Russian).
    # English columns define the target schema, but some live workbook rows have
    # blank English formula cells and populated raw Russian source cells.
    col_map = {}
    target_cols_used = set()
    fallback_fill_sources: dict[str, list[str]] = {}

    # Define priority order: English columns first, then Russian fallbacks
    column_targets = [
        (["orderid", "order_id"], "order_id"),
        (["date", "order_date"], "order_date"),
        (["kaspi_offer_name"], "kaspi_offer_name"),
        (["kaspi_article", "article", "артикул"], "kaspi_article"),
        (["sku_id", "skuid"], "sku_id"),
        (["sku_key", "skukey"], "sku_key"),
        (["my_size", "mysize", "size"], "my_size"),
        (["quantity", "qty"], "quantity"),
        (["sell_price_kzt", "price"], "sell_price_kzt"),
        (["store_name", "storename", "store"], "store_name"),
        (["return", "return_flag"], "return_flag"),
        (["total_net_rev", "net_rev"], "net_rev"),
        (["delivery_fee_kzt", "delivery_fee"], "delivery_fee"),
        (["delivery_fee_seller"], "delivery_fee_seller"),
        (["delivery_fee_buyer"], "delivery_fee_buyer"),
        (["total_price", "totalprice"], "total_price"),
    ]

    # Russian fallbacks. If the English target exists, use these row-by-row only
    # where the English cell is blank.
    russian_fallbacks = {
        "№ заказа": "order_id",
        "дата поступления заказа": "order_date",
        "название товара в kaspi магазине": "kaspi_offer_name",
        "количество": "quantity",
        "сумма": "sell_price_kzt",
        "стоимость доставки для продавца": "delivery_fee_seller",
        "стоимость доставки для покупателя": "delivery_fee_buyer",
    }

    # First pass: map English columns
    for col in df.columns:
        col_lower = col.lower().strip()
        for source_list, target in column_targets:
            if col_lower in source_list and target not in target_cols_used:
                col_map[col] = target
                target_cols_used.add(target)
                break

    # Second pass: map Russian fallbacks only if target not already used
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in russian_fallbacks:
            target = russian_fallbacks[col_lower]
            fallback_fill_sources.setdefault(target, []).append(col)
            if target not in target_cols_used:
                col_map[col] = target
                target_cols_used.add(target)

    df = df.rename(columns=col_map)

    def _blank_mask(series: pd.Series) -> pd.Series:
        text = series.astype(str).str.strip().str.lower()
        return series.isna() | text.isin({"", "nan", "none", "null"})

    for target, source_cols in fallback_fill_sources.items():
        if target not in df.columns:
            continue
        df[target] = df[target].astype("object")
        for source_col in source_cols:
            if source_col not in df.columns:
                continue
            target_blank = _blank_mask(df[target])
            source_present = ~_blank_mask(df[source_col])
            df.loc[target_blank & source_present, target] = df.loc[target_blank & source_present, source_col]

    # Validate required columns
    required = ["order_id", "order_date", "kaspi_offer_name", "quantity"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    # Convert to list of dicts
    records = []
    for _, row in df.iterrows():
        # Get order_id
        order_id = row.get("order_id")
        if pd.isna(order_id):
            continue
        order_id = str(int(order_id)) if isinstance(order_id, float) else str(order_id).strip()

        # Get kaspi_offer_name (required for dedup)
        kaspi_offer_name = row.get("kaspi_offer_name")
        if pd.isna(kaspi_offer_name):
            continue
        kaspi_offer_name = str(kaspi_offer_name).strip()

        # Get SKU info
        kaspi_article = row.get("kaspi_article")
        kaspi_article = str(kaspi_article).strip() if not pd.isna(kaspi_article) else None

        sku_id = row.get("sku_id")
        sku_id = str(sku_id).strip() if not pd.isna(sku_id) else None

        sku_key = row.get("sku_key")
        sku_key = str(sku_key).strip() if not pd.isna(sku_key) else None

        my_size = row.get("my_size")
        my_size = str(my_size).strip() if not pd.isna(my_size) else None
        product_type = None
        if sku_key and "_" in sku_key:
            product_type = sku_key.split("_", 1)[0]
            sku_key = normalize_sku_key(sku_key)
        elif sku_id and "_" in sku_id:
            product_type = sku_id.split("_", 1)[0]

        my_size = normalize_size(my_size, product_type=product_type)
        if my_size is None:
            inferred_from_sku = infer_size_from_sku_id(sku_id)
            my_size = normalize_size(inferred_from_sku, product_type=product_type)
        if my_size is None:
            my_size = infer_size_from_offer_name(kaspi_offer_name, product_type=product_type)

        # Get date
        order_date = row.get("order_date")
        order_event_at = order_date
        if pd.isna(order_date):
            continue
        if isinstance(order_date, datetime):
            order_event_at = order_date
            order_date = order_date.date()
        elif isinstance(order_date, str):
            try:
                parsed_order_dt = datetime.strptime(order_date, "%Y-%m-%d")
                order_event_at = parsed_order_dt
                order_date = parsed_order_dt.date()
            except ValueError:
                try:
                    parsed_order_dt = datetime.strptime(order_date, "%d.%m.%Y")
                    order_event_at = parsed_order_dt
                    order_date = parsed_order_dt.date()
                except ValueError:
                    continue

        alias = apply_rombik_kid30_alias(
            sku_key=sku_key,
            sku_id=sku_id,
            my_size=my_size,
            event_at=order_event_at,
            kaspi_article=kaspi_article,
            kaspi_offer_name=kaspi_offer_name,
        )
        sku_key = alias["sku_key"]
        sku_id = alias["sku_id"]
        my_size = alias["my_size"]

        # Get quantity
        quantity = row.get("quantity", 1)
        if pd.isna(quantity):
            quantity = 1
        quantity = int(quantity)

        # Get price
        sell_price = row.get("sell_price_kzt")
        sell_price = float(sell_price) if not pd.isna(sell_price) else None

        # Get store
        store_name = row.get("store_name", "UNIVERSAL")
        store_code = normalize_store_code(store_name)

        # Get return flag
        return_flag = row.get("return_flag", 0)
        if pd.isna(return_flag):
            return_flag = 0
        return_flag = int(return_flag) if return_flag else 0

        # Get other fields
        net_rev = row.get("net_rev")
        net_rev = float(net_rev) if not pd.isna(net_rev) else None

        delivery_fee_seller = row.get("delivery_fee_seller")
        delivery_fee_buyer = row.get("delivery_fee_buyer")
        delivery_fee_raw = row.get("delivery_fee")

        def _coerce_float(value):
            if pd.isna(value):
                return None
            if isinstance(value, str):
                cleaned = value.replace("\u00a0", "").replace(" ", "")
                if cleaned.count(",") == 1 and cleaned.count(".") == 0:
                    cleaned = cleaned.replace(",", ".")
                try:
                    return float(cleaned)
                except ValueError:
                    return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        delivery_fee_seller = _coerce_float(delivery_fee_seller)
        delivery_fee_buyer = _coerce_float(delivery_fee_buyer)
        delivery_fee = _coerce_float(delivery_fee_raw)

        # Prefer seller-paid fee; fall back to legacy delivery_fee_kzt, then buyer fee.
        if delivery_fee_seller is not None:
            delivery_fee = delivery_fee_seller
        elif delivery_fee is None and delivery_fee_buyer is not None:
            delivery_fee = delivery_fee_buyer

        records.append({
            "order_id": order_id,
            "order_date": order_date,
            "kaspi_offer_name": kaspi_offer_name,
            "kaspi_article": kaspi_article,
            "sku_id": sku_id,
            "sku_key": sku_key,
            "my_size": my_size,
            "quantity": quantity,
            "sell_price_kzt": sell_price,
            "store_code": store_code,
            "return_flag": return_flag,
            "net_rev": net_rev,
            "delivery_fee": delivery_fee,
            "delivery_fee_seller": delivery_fee_seller,
            "delivery_fee_buyer": delivery_fee_buyer,
        })

    return records


def get_unmapped_offers(
    xlsx_path: str,
    sheet_name: str = "SALES_KSP_CRM_1",
    db_path: Optional[Path] = None,
) -> list[dict]:
    """
    Return list of kaspi_offer_name not found in dim_sku_size.

    Args:
        xlsx_path: Path to sales Excel file
        sheet_name: Sheet name
        db_path: Database path

    Returns:
        List of dicts with unmapped offer info: {kaspi_offer_name, order_count}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    records = parse_sales_excel(xlsx_path, sheet_name)

    # Count offers without sku_id
    unmapped = {}
    for rec in records:
        if not rec["sku_id"]:
            offer = rec["kaspi_offer_name"]
            if offer not in unmapped:
                unmapped[offer] = {"kaspi_offer_name": offer, "order_count": 0}
            unmapped[offer]["order_count"] += 1

    return sorted(unmapped.values(), key=lambda x: -x["order_count"])


def ingest_sales(
    xlsx_path: str,
    sheet_name: str = "SALES_KSP_CRM_1",
    apply_to_ledger: bool = True,
    source_file: str = None,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Ingest sales from Excel to sales_fact_v2 and stock_ledger.

    Deduplication key: (order_id, store_code, kaspi_offer_name, sku_key, my_size)

    Steps:
    1. Parse Excel
    2. Deduplicate on unique key
    3. Insert new records to sales_fact_v2
    4. For each new sale: add SALE event to stock_ledger (qty_change = -quantity)
    5. For returns (return_flag=1): add RETURN event (qty_change = +quantity)

    Args:
        xlsx_path: Path to sales Excel file
        sheet_name: Sheet name
        apply_to_ledger: Whether to create ledger events (default: True)
        source_file: Source file name for tracking
        db_path: Database path

    Returns:
        Dict with counts: {inserted, skipped, returns_processed, unmapped, errors}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    if source_file is None:
        source_file = Path(xlsx_path).name

    records = parse_sales_excel(xlsx_path, sheet_name)

    result = {
        "inserted": 0,
        "skipped": 0,
        "returns_processed": 0,
        "unmapped": [],
        "ledger_events": 0,
        "errors": [],
    }

    # Collect ledger events to add after main transaction
    pending_ledger_events = []

    with get_db(db_path) as conn:
        for rec in records:
            order_id = rec["order_id"]
            store_code = rec["store_code"]
            kaspi_offer_name = rec["kaspi_offer_name"]

            sku_key, sku_id, my_size = resolve_sales_identity(
                conn,
                rec.get("sku_id"),
                rec.get("sku_key"),
                rec.get("my_size"),
                kaspi_offer_name,
                store_code,
            )

            # Skip if missing resolved identity
            if not sku_id or not sku_key or not my_size:
                if kaspi_offer_name not in [u["offer"] for u in result["unmapped"]]:
                    result["unmapped"].append({"offer": kaspi_offer_name, "order_id": order_id})
                continue

            # Check for existing record (dedup)
            existing = conn.execute("""
                SELECT sale_id, return_flag FROM sales_fact_v2
                WHERE order_id = ? AND store_code = ? AND kaspi_offer_name = ?
                  AND sku_key = ? AND my_size = ?
            """, (
                order_id,
                store_code,
                kaspi_offer_name,
                sku_key,
                my_size,
            )).fetchone()

            if not existing:
                existing = conn.execute("""
                    SELECT sale_id, return_flag FROM sales_fact_v2
                    WHERE order_id = ? AND sku_id = ? AND store_code = ? AND kaspi_offer_name = ?
                """, (order_id, sku_id, store_code, kaspi_offer_name)).fetchone()

            if existing:
                # Check if return status changed
                old_return_flag = existing["return_flag"]
                new_return_flag = rec["return_flag"]

                if old_return_flag != new_return_flag and new_return_flag == 1:
                    # Update to returned status
                    conn.execute("""
                        UPDATE sales_fact_v2
                        SET return_flag = 1, status = 'RETURNED', return_date = ?
                        WHERE sale_id = ?
                    """, (date.today().isoformat(), existing["sale_id"]))

                    # Queue RETURN event to ledger (stock increase)
                    if apply_to_ledger:
                        pending_ledger_events.append({
                            "event_type": "RETURN",
                            "sku_id": sku_id,
                            "qty_change": rec["quantity"],
                            "event_date": date.today(),
                            "store_code": store_code,
                            "reference_id": order_id,
                            "reference_type": "SALE",
                            "kaspi_offer_name": kaspi_offer_name,
                            "notes": "Return detected on re-ingest",
                            "input_source": "IMPORT",
                        })

                    result["returns_processed"] += 1
                else:
                    result["skipped"] += 1
                continue

            # Insert new sale
            try:
                cursor = conn.execute("""
                    INSERT INTO sales_fact_v2 (
                        order_id, order_date, sku_key, sku_id, my_size,
                        kaspi_offer_name, store_code, quantity, sell_price_kzt,
                        delivery_fee, net_rev, status, return_flag, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    order_id,
                    rec["order_date"].isoformat() if isinstance(rec["order_date"], date) else rec["order_date"],
                    sku_key,
                    sku_id,
                    my_size,
                    kaspi_offer_name,
                    store_code,
                    rec["quantity"],
                    rec["sell_price_kzt"],
                    rec["delivery_fee"],
                    rec["net_rev"],
                    "RETURNED" if rec["return_flag"] else "DELIVERED",
                    rec["return_flag"],
                    source_file,
                ))

                result["inserted"] += 1

                # Queue ledger events
                if apply_to_ledger:
                    if rec["return_flag"]:
                        # This is a historical return - add both SALE and RETURN events
                        pending_ledger_events.append({
                            "event_type": "SALE",
                            "sku_id": sku_id,
                            "qty_change": -rec["quantity"],
                            "event_date": rec["order_date"],
                            "store_code": store_code,
                            "reference_id": order_id,
                            "reference_type": "SALE",
                            "kaspi_offer_name": kaspi_offer_name,
                            "notes": "Historical sale with return",
                            "input_source": "IMPORT",
                        })
                        pending_ledger_events.append({
                            "event_type": "RETURN",
                            "sku_id": sku_id,
                            "qty_change": rec["quantity"],
                            "event_date": rec["order_date"],
                            "store_code": store_code,
                            "reference_id": order_id,
                            "reference_type": "SALE",
                            "kaspi_offer_name": kaspi_offer_name,
                            "notes": "Historical return",
                            "input_source": "IMPORT",
                        })
                        result["returns_processed"] += 1
                    else:
                        # Normal sale - SALE event (stock decrease)
                        pending_ledger_events.append({
                            "event_type": "SALE",
                            "sku_id": sku_id,
                            "qty_change": -rec["quantity"],
                            "event_date": rec["order_date"],
                            "store_code": store_code,
                            "reference_id": order_id,
                            "reference_type": "SALE",
                            "kaspi_offer_name": kaspi_offer_name,
                            "input_source": "IMPORT",
                        })

            except sqlite3.IntegrityError as e:
                # Duplicate - should be caught by check above
                result["skipped"] += 1
            except Exception as e:
                result["errors"].append(f"Order {order_id}: {str(e)}")

    # Now add ledger events outside the main transaction
    for event in pending_ledger_events:
        try:
            add_ledger_event(
                event_type=event["event_type"],
                sku_id=event["sku_id"],
                qty_change=event["qty_change"],
                event_date=event["event_date"],
                store_code=inventory_pool_store_code(),
                reference_id=event["reference_id"],
                reference_type=event["reference_type"],
                kaspi_offer_name=event.get("kaspi_offer_name"),
                notes=event.get("notes"),
                input_source=event["input_source"],
                db_path=db_path,
            )
            result["ledger_events"] += 1
        except Exception as e:
            result["errors"].append(f"Ledger event for {event['sku_id']}: {str(e)}")

    # Log audit entry for batch import
    if result["inserted"] > 0:
        log_audit(
            table_name="sales_fact_v2",
            record_id=f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            field_name="*",
            old_value=None,
            new_value=f"{result['inserted']} sales from {source_file}",
            change_type="INSERT",
            reason=f"Batch import: {result['inserted']} inserted, {result['skipped']} skipped",
            source="IMPORT",
            db_path=db_path,
        )

    return result


def ingest_sales_to_fact_sales(
    xlsx_path: str,
    sheet_name: str = "SALES_KSP_CRM_1",
    dry_run: bool = False,
    source_file: str | None = None,
    db_path: Optional[Path] = None,
    from_date: str | date | None = None,
    to_date: str | date | None = None,
) -> dict:
    """
    Ingest sales from CRM sheet into fact_sales with v8 economics.

    Deduplication key: (order_id, store_code, kaspi_offer_name, sku_key, my_size)
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    if source_file is None:
        source_file = Path(xlsx_path).name

    records = parse_sales_excel(xlsx_path, sheet_name)
    if from_date is not None or to_date is not None:
        from_key = from_date.isoformat() if isinstance(from_date, date) else str(from_date) if from_date else None
        to_key = to_date.isoformat() if isinstance(to_date, date) else str(to_date) if to_date else None

        def _date_key(rec: dict) -> str:
            value = rec.get("order_date")
            return value.isoformat() if isinstance(value, date) else str(value)

        records = [
            rec
            for rec in records
            if (from_key is None or _date_key(rec) >= from_key)
            and (to_key is None or _date_key(rec) <= to_key)
        ]

    stats = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "unmapped": [],
        "min_date": None,
        "max_date": None,
    }

    with get_db(db_path) as conn:
        dates = [rec.get("order_date") for rec in records if rec.get("order_date")]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None

        existing_by_key: dict[tuple, int] = {}
        existing_by_unique: dict[tuple, int] = {}
        if min_date and max_date:
            existing_rows = conn.execute(
                """
                SELECT id, order_id, store_code, kaspi_offer_name, sku_key, my_size, sku_id
                FROM fact_sales
                WHERE order_date BETWEEN ? AND ?
                """,
                (min_date, max_date),
            ).fetchall()
            for row in existing_rows:
                key = (
                    str(row["order_id"]),
                    str(row["store_code"]),
                    str(row["kaspi_offer_name"] or ""),
                    str(row["sku_key"] or ""),
                    str(row["my_size"] or ""),
                )
                unique_key = (
                    str(row["order_id"]),
                    str(row["store_code"]),
                    str(row["kaspi_offer_name"] or ""),
                    str(row["sku_id"] or ""),
                )
                existing_by_key[key] = row["id"]
                existing_by_unique[unique_key] = row["id"]

        sku_meta = {
            row["sku_key"]: {
                "base_cost_cny": row["base_cost_cny"],
                "weight_kg": row["weight_kg"],
                "product_type": row["product_type"],
                "cogs_kzt": row["cogs_kzt"],
            }
            for row in conn.execute(
                """
                SELECT sku_key, base_cost_cny, weight_kg, product_type, cogs_kzt
                FROM dim_sku
                """
            ).fetchall()
        }
        size_rows = conn.execute(
            "SELECT sku_id, sku_key, my_size FROM dim_sku_size"
        ).fetchall()
        size_lookup = {
            row["sku_id"]: {"sku_key": row["sku_key"], "my_size": row["my_size"]}
            for row in size_rows
        }
        size_lookup_by_key = {
            (row["sku_key"], row["my_size"]): row["sku_id"]
            for row in size_rows
        }
        seen_keys: set[tuple] = set()
        updates: list[tuple] = []
        inserts: list[tuple] = []

        for rec in records:
            order_id = rec["order_id"]
            order_date = rec["order_date"]
            store_code = rec["store_code"]
            kaspi_offer_name = rec["kaspi_offer_name"]
            quantity = int(rec["quantity"] or 0)

            if quantity <= 0:
                stats["skipped"] += 1
                continue

            resolution = _resolve_sales_identity_detail(
                conn,
                rec.get("sku_id"),
                rec.get("sku_key"),
                rec.get("my_size"),
                kaspi_offer_name=kaspi_offer_name,
                store_code=store_code,
            )
            sku_key, sku_id, my_size = resolution.sku_key, resolution.sku_id, resolution.my_size

            if not sku_key or not my_size or not sku_id:
                stats["unmapped"].append({"offer": kaspi_offer_name, "order_id": order_id})
                stats["skipped"] += 1
                continue

            if not resolution.offer_name_mapping_sku_key_only:
                size_info = size_lookup.get(sku_id)
                if size_info:
                    sku_key = size_info["sku_key"]
                    my_size = size_info["my_size"]
                else:
                    resolved_id = size_lookup_by_key.get((sku_key, my_size))
                    if resolved_id:
                        sku_id = resolved_id
                    else:
                        stats["unmapped"].append({"offer": kaspi_offer_name, "order_id": order_id})
                        stats["skipped"] += 1
                        continue

            sku_info = sku_meta.get(sku_key)
            if not sku_info:
                stats["errors"].append(f"Missing sku_key in dim_sku: {sku_key}")
                stats["skipped"] += 1
                continue

            sell_price = rec.get("sell_price_kzt")
            if sell_price is None:
                stats["errors"].append(f"Missing sell_price_kzt for order {order_id}")
                stats["skipped"] += 1
                continue

            base_cost = sku_info.get("base_cost_cny") or 0
            weight_kg = sku_info.get("weight_kg") or 0
            cogs_unit = None
            if base_cost and weight_kg:
                cogs_unit = calc_cogs(base_cost, weight_kg)
            elif sku_info.get("cogs_kzt"):
                cogs_unit = float(sku_info["cogs_kzt"])

            if cogs_unit is None:
                stats["errors"].append(f"Missing COGS for sku_key {sku_key}")
                stats["skipped"] += 1
                continue

            dedupe_key = (
                str(order_id or ""),
                str(store_code or ""),
                str(kaspi_offer_name or ""),
                str(sku_key or ""),
                str(my_size or ""),
            )
            if dedupe_key in seen_keys:
                stats["skipped"] += 1
                continue
            seen_keys.add(dedupe_key)

            delivery_fee = rec.get("delivery_fee")
            if delivery_fee is None or delivery_fee <= 0:
                delivery_fee = calc_delivery_fee(
                    sell_price,
                    weight_kg=weight_kg,
                    delivery_type="city",
                )

            net_rev_unit = calc_net_rev(
                sell_price,
                delivery_fee=delivery_fee,
                weight_kg=weight_kg,
                as_of_date=order_date,
            )

            profit_unit = net_rev_unit - cogs_unit if cogs_unit is not None else None
            line_net_rev = net_rev_unit * quantity
            cogs_line = cogs_unit * quantity if cogs_unit is not None else None
            profit_line = profit_unit * quantity if profit_unit is not None else None

            existing_id = existing_by_key.get(dedupe_key)
            if not existing_id:
                existing_id = existing_by_unique.get(
                    (
                        str(order_id or ""),
                        str(store_code or ""),
                        str(kaspi_offer_name or ""),
                        str(sku_id or ""),
                    )
                )

            payload = (
                order_id,
                kaspi_offer_name,
                store_code,
                order_date.isoformat() if isinstance(order_date, date) else order_date,
                sku_key,
                sku_id,
                my_size,
                quantity,
                float(sell_price),
                sku_info.get("product_type") or "CL",
                "Kaspi",
                delivery_fee,
                net_rev_unit,
                line_net_rev,
                cogs_unit,
                cogs_line,
                profit_unit,
                profit_line,
                "KSP",
            )

            if existing_id:
                if not dry_run:
                    updates.append(
                        (
                            kaspi_offer_name,
                            store_code,
                            order_date.isoformat() if isinstance(order_date, date) else order_date,
                            sku_key,
                            sku_id,
                            my_size,
                            quantity,
                            float(sell_price),
                            sku_info.get("product_type") or "CL",
                            "Kaspi",
                            delivery_fee,
                            net_rev_unit,
                            line_net_rev,
                            cogs_unit,
                            cogs_line,
                            profit_unit,
                            profit_line,
                            "KSP",
                            existing_id,
                        )
                    )
                stats["updated"] += 1
            else:
                if not dry_run:
                    inserts.append(payload)
                stats["inserted"] += 1

            if order_date:
                iso_date = order_date.isoformat() if isinstance(order_date, date) else str(order_date)
                if stats["min_date"] is None or iso_date < stats["min_date"]:
                    stats["min_date"] = iso_date
                if stats["max_date"] is None or iso_date > stats["max_date"]:
                    stats["max_date"] = iso_date

        if not dry_run:
            if updates:
                conn.executemany(
                    """
                    UPDATE fact_sales
                    SET kaspi_offer_name = ?,
                        store_code = ?,
                        order_date = ?,
                        sku_key = ?,
                        sku_id = ?,
                        my_size = ?,
                        quantity = ?,
                        sell_price_kzt = ?,
                        product_type = ?,
                        channel = ?,
                        delivery_fee = ?,
                        net_rev_unit = ?,
                        line_net_rev = ?,
                        cogs_unit = ?,
                        cogs_line = ?,
                        profit_unit = ?,
                        profit_line = ?,
                        channel_code = ?
                    WHERE id = ?
                    """,
                    updates,
                )
            if inserts:
                conn.executemany(
                    """
                    INSERT INTO fact_sales (
                        order_id, kaspi_offer_name, store_code, order_date,
                        sku_key, sku_id, my_size, quantity, sell_price_kzt,
                        product_type, channel, delivery_fee,
                        net_rev_unit, line_net_rev, cogs_unit, cogs_line,
                        profit_unit, profit_line, channel_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    inserts,
                )

    return stats


def update_returns_from_api(
    api_returns: list[dict],
    db_path: Optional[Path] = None,
) -> int:
    """
    Update sales_fact_v2 with return status from API.

    For each return:
    1. Find matching sale in sales_fact_v2
    2. Update status = 'RETURNED', return_flag = 1, return_date = today
    3. Add RETURN event to stock_ledger if not already exists
    4. Log to fact_input_audit

    Args:
        api_returns: List of return dicts with order_id, sku_id, store_code
        db_path: Database path

    Returns:
        Number of returns processed
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    processed = 0
    pending_ledger_events = []

    with get_db(db_path) as conn:
        for ret in api_returns:
            order_id = ret.get("order_id")
            sku_id = ret.get("sku_id")
            store_code = ret.get("store_code", "UNIVERSAL")

            if not order_id or not sku_id:
                continue

            # Find matching sale
            sale = conn.execute("""
                SELECT sale_id, kaspi_offer_name, quantity, return_flag
                FROM sales_fact_v2
                WHERE order_id = ? AND sku_id = ? AND store_code = ?
            """, (order_id, sku_id, store_code)).fetchone()

            if not sale:
                continue

            # Skip if already returned
            if sale["return_flag"] == 1:
                continue

            # Update sale record
            conn.execute("""
                UPDATE sales_fact_v2
                SET status = 'RETURNED', return_flag = 1,
                    return_date = ?, api_updated_at = ?
                WHERE sale_id = ?
            """, (date.today().isoformat(), datetime.now().isoformat(), sale["sale_id"]))

            # Check for existing RETURN event
            existing_return = conn.execute("""
                SELECT ledger_id FROM stock_ledger
                WHERE reference_id = ? AND reference_type = 'SALE'
                  AND event_type = 'RETURN' AND sku_id = ?
            """, (order_id, sku_id)).fetchone()

            if not existing_return:
                # Queue RETURN event to ledger
                pending_ledger_events.append({
                    "sku_id": sku_id,
                    "qty_change": sale["quantity"],
            "store_code": store_code,
                    "reference_id": order_id,
                    "kaspi_offer_name": sale["kaspi_offer_name"],
                })

            # Log to audit (queue for after transaction)
            sale_id = sale["sale_id"]

            processed += 1

    # Log audit entries outside transaction for consistency
    # Note: We can't queue individual audit entries above due to scope, so we log generically
    # The update_returns_from_api function logs all returns processed in this batch
    if processed > 0:
        log_audit(
            table_name="sales_fact_v2",
            record_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            field_name="return_flag",
            old_value="0",
            new_value="1",
            change_type="UPDATE",
            reason=f"{processed} returns processed from API",
            source="API",
            db_path=db_path,
        )

    # Add ledger events outside the main transaction
    for event in pending_ledger_events:
        add_ledger_event(
            event_type="RETURN",
            sku_id=event["sku_id"],
            qty_change=event["qty_change"],
            event_date=date.today(),
            store_code=inventory_pool_store_code(),
            reference_id=event["reference_id"],
            reference_type="SALE",
            kaspi_offer_name=event["kaspi_offer_name"],
            notes="Return from API",
            input_source="API",
            db_path=db_path,
        )

    return processed
