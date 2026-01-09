"""
TASK-176: Sales Ingestion Module (Phase 10)

Parses sales Excel files and ingests to sales_fact_v2 and stock_ledger.

Key constraint: Unique key is (order_id, sku_id, store_code, kaspi_offer_name)
- Same order can have same kaspi_offer_name with qty=2 but different sizes
- Same order can have different kaspi_offer_name with same sku_id

Tables used:
- sales_fact_v2: Enhanced sales with return tracking
- stock_ledger: Event-sourced stock changes (SALE/RETURN events)
- dim_sku_size: Size definitions for a SKU
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event, log_audit


# Store code normalization map
STORE_CODE_MAP = {
    "universal": "UNIVERSAL",
    "acmewear": "ACMEWEAR",
    "store-d": "11KZ",
    "11_kz": "11KZ",
    "samson": "SAMSON",
    "abyx": "ABYX",
}


def normalize_store_code(store_name: str) -> str:
    """Normalize store name to store code."""
    if not store_name or pd.isna(store_name):
        return "UNIVERSAL"

    clean = str(store_name).lower().strip().replace(" ", "_")
    return STORE_CODE_MAP.get(clean, store_name.upper())


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

    # Column name normalization (handle both English and Russian)
    # IMPORTANT: Only rename columns that don't create duplicates (English takes priority)
    col_map = {}
    target_cols_used = set()

    # Define priority order: English columns first, then Russian fallbacks
    column_targets = [
        (["orderid", "order_id"], "order_id"),
        (["date", "order_date"], "order_date"),
        (["kaspi_offer_name"], "kaspi_offer_name"),
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

    # Russian fallbacks (only used if English not found)
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
            if target not in target_cols_used:
                col_map[col] = target
                target_cols_used.add(target)

    df = df.rename(columns=col_map)

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
        sku_id = row.get("sku_id")
        sku_id = str(sku_id).strip() if not pd.isna(sku_id) else None

        sku_key = row.get("sku_key")
        sku_key = str(sku_key).strip() if not pd.isna(sku_key) else None

        my_size = row.get("my_size")
        my_size = str(my_size).strip() if not pd.isna(my_size) else None

        # Get date
        order_date = row.get("order_date")
        if pd.isna(order_date):
            continue
        if isinstance(order_date, datetime):
            order_date = order_date.date()
        elif isinstance(order_date, str):
            try:
                order_date = datetime.strptime(order_date, "%Y-%m-%d").date()
            except ValueError:
                try:
                    order_date = datetime.strptime(order_date, "%d.%m.%Y").date()
                except ValueError:
                    continue

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

    Deduplication key: (order_id, sku_id, store_code, kaspi_offer_name)

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
            sku_id = rec["sku_id"]
            store_code = rec["store_code"]
            kaspi_offer_name = rec["kaspi_offer_name"]

            # Skip if missing sku_id
            if not sku_id:
                if kaspi_offer_name not in [u["offer"] for u in result["unmapped"]]:
                    result["unmapped"].append({"offer": kaspi_offer_name, "order_id": order_id})
                continue

            # Check for existing record (dedup)
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
                    rec["sku_key"],
                    sku_id,
                    rec["my_size"],
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
                store_code=event["store_code"],
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
            store_code=event["store_code"],
            reference_id=event["reference_id"],
            reference_type="SALE",
            kaspi_offer_name=event["kaspi_offer_name"],
            notes="Return from API",
            input_source="API",
            db_path=db_path,
        )

    return processed
