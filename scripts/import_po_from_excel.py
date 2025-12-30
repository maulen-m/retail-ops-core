#!/usr/bin/env python3
"""
TASK-188: PO Import Script (Phase 10)

Imports PO data from the Inbound template Excel file.

Sheets:
- PO_headers: PO header records (VendorID, dates, FX rates, costs)
- PO_book: PO line items (SKU, qty, cost)
- Inventory_move: Actual receipts (creates INBOUND events)

Usage:
    python scripts/import_po_from_excel.py excel/Inbound_template_09.12.2025.xlsx
    python scripts/import_po_from_excel.py excel/Inbound_template_09.12.2025.xlsx --dry-run
    python scripts/import_po_from_excel.py excel/Inbound_template_09.12.2025.xlsx --skip-inventory
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event, log_audit


def parse_date(val) -> Optional[date]:
    """Parse date from various formats."""
    if pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                continue
    return None


def import_po_headers(
    xlsx_path: str,
    dry_run: bool = False,
    verbose: bool = True,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Import PO headers from Excel.

    Returns dict with {imported, updated, skipped, errors}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    df = pd.read_excel(xlsx_path, sheet_name="PO_headers")

    result = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    # Column mapping
    col_map = {
        "PO_Id": "po_id",
        "VendorID": "supplier_code",
        "Message_date": "message_date",
        "Ship_Date_Seller": "ship_date_seller",
        "Ship_Date_Cargo": "ship_date_cargo",
        "ALM_arrival_date": "alm_arrival_date",
        "Ast_arrival_nom": "ast_arrival_nom",
        "Alm_arrival_real": "alm_arrival_real",
        "Ast_arrival_date": "ast_arrival_real",
        "Archive_alm_arrival": "archive_alm_arrival",
        "Archive_ast_arrival": "archive_ast_arrival",
        "FX_CNYKZT": "fx_rate_cny_actual",
        "FX_USDKZT_REAL": "fx_rate_usd_kzt",
        "Total_order_weight_nom": "weight_nom_kg",
        "Total_order_weight_real": "weight_real_kg",
        "status_real": "status",
        "Total_OrderCost_KZT": "total_cost_kzt_supplier",
        "Total_DeliveryCost_USD_real": "cargo_cost_usd",
        "Total_FreightCost_KZT_real": "cargo_cost_kzt",
        "Internal_order_code": "notes",
    }

    with get_db(db_path) as conn:
        for _, row in df.iterrows():
            po_id = row.get("PO_Id")
            if pd.isna(po_id) or not po_id:
                result["skipped"] += 1
                continue

            po_id = str(po_id).strip()

            # Check if PO exists
            existing = conn.execute(
                "SELECT po_id FROM po_header WHERE po_id = ?", (po_id,)
            ).fetchone()

            # Build record
            record = {}
            for excel_col, db_col in col_map.items():
                if excel_col in row:
                    val = row[excel_col]
                    if pd.isna(val):
                        continue

                    # Handle date fields
                    if "date" in db_col.lower() or "arrival" in db_col.lower():
                        val = parse_date(val)
                        if val:
                            val = val.isoformat()
                        else:
                            continue
                    # Handle numeric fields
                    elif db_col in ["fx_rate_cny_actual", "fx_rate_usd_kzt",
                                    "weight_nom_kg", "weight_real_kg",
                                    "total_cost_kzt_supplier", "cargo_cost_usd",
                                    "cargo_cost_kzt"]:
                        try:
                            val = float(val)
                        except (ValueError, TypeError):
                            continue
                    else:
                        val = str(val).strip()

                    record[db_col] = val

            if not record:
                result["skipped"] += 1
                continue

            if dry_run:
                if existing:
                    result["updated"] += 1
                else:
                    result["imported"] += 1
                continue

            try:
                if existing:
                    # Update existing PO
                    set_clause = ", ".join(f"{k} = ?" for k in record.keys() if k != "po_id")
                    values = [v for k, v in record.items() if k != "po_id"]
                    values.append(po_id)

                    conn.execute(f"""
                        UPDATE po_header SET {set_clause}, updated_at = datetime('now')
                        WHERE po_id = ?
                    """, values)
                    result["updated"] += 1
                else:
                    # Insert new PO
                    record["po_id"] = po_id
                    cols = ", ".join(record.keys())
                    placeholders = ", ".join("?" * len(record))
                    conn.execute(f"""
                        INSERT INTO po_header ({cols}) VALUES ({placeholders})
                    """, list(record.values()))
                    result["imported"] += 1

                    # Log audit
                    log_audit(
                        table_name="po_header",
                        record_id=po_id,
                        field_name="*",
                        old_value=None,
                        new_value=f"Imported from {Path(xlsx_path).name}",
                        change_type="INSERT",
                        source="IMPORT",
                        db_path=db_path,
                    )

            except Exception as e:
                result["errors"].append(f"{po_id}: {str(e)}")

    if verbose:
        print(f"  PO Headers: {result['imported']} imported, {result['updated']} updated, {result['skipped']} skipped")
        if result["errors"]:
            print(f"  Errors: {len(result['errors'])}")

    return result


def import_po_lines(
    xlsx_path: str,
    dry_run: bool = False,
    verbose: bool = True,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Import PO lines from Excel.

    Returns dict with {imported, updated, skipped, errors}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    df = pd.read_excel(xlsx_path, sheet_name="PO_book")

    result = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }

    with get_db(db_path) as conn:
        for _, row in df.iterrows():
            po_id = row.get("PO_Id")
            sku_id = row.get("SKU_ID")

            if pd.isna(po_id) or pd.isna(sku_id):
                result["skipped"] += 1
                continue

            po_id = str(po_id).strip()
            sku_id = str(sku_id).strip()

            # Extract values
            sku_key = str(row.get("SKU_KEY", "")).strip() if not pd.isna(row.get("SKU_KEY")) else None
            my_size = str(row.get("MY_SIZE", "")).strip() if not pd.isna(row.get("MY_SIZE")) else None
            order_qty = int(row.get("Order_Quantity", 0)) if not pd.isna(row.get("Order_Quantity")) else 0
            received_qty = int(row.get("Received_Qty", 0)) if not pd.isna(row.get("Received_Qty")) else 0
            unit_cost_cny = float(row.get("UnitCost_CNY", 0)) if not pd.isna(row.get("UnitCost_CNY")) else 0

            if order_qty <= 0:
                result["skipped"] += 1
                continue

            # Check if line exists
            existing = conn.execute("""
                SELECT po_line_id FROM po_line
                WHERE po_id = ? AND sku_id = ?
            """, (po_id, sku_id)).fetchone()

            if dry_run:
                if existing:
                    result["updated"] += 1
                else:
                    result["imported"] += 1
                continue

            try:
                if existing:
                    # Update existing line
                    conn.execute("""
                        UPDATE po_line
                        SET order_qty = ?, received_qty = ?, unit_cost_cny = ?
                        WHERE po_line_id = ?
                    """, (order_qty, received_qty, unit_cost_cny, existing["po_line_id"]))
                    result["updated"] += 1
                else:
                    # Insert new line
                    # Derive sku_key and my_size if not provided
                    if not sku_key or not my_size:
                        parts = sku_id.rsplit("_", 1)
                        if len(parts) == 2:
                            if not sku_key:
                                sku_key = parts[0]
                            if not my_size:
                                my_size = parts[1]
                        else:
                            if not sku_key:
                                sku_key = sku_id
                            if not my_size:
                                my_size = "UNKNOWN"

                    conn.execute("""
                        INSERT INTO po_line (
                            po_id, sku_key, sku_id, my_size, order_qty,
                            received_qty, unit_cost_cny, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        po_id, sku_key, sku_id, my_size, order_qty,
                        received_qty, unit_cost_cny,
                        "RECEIVED" if received_qty >= order_qty else ("PARTIAL" if received_qty > 0 else "PENDING")
                    ))
                    result["imported"] += 1

            except Exception as e:
                result["errors"].append(f"{po_id}/{sku_id}: {str(e)}")

    if verbose:
        print(f"  PO Lines: {result['imported']} imported, {result['updated']} updated, {result['skipped']} skipped")
        if result["errors"]:
            print(f"  Errors: {len(result['errors'])}")

    return result


def import_inventory_moves(
    xlsx_path: str,
    dry_run: bool = False,
    verbose: bool = True,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Import inventory movements (creates INBOUND ledger events).

    Returns dict with {events_created, skipped, errors}
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    df = pd.read_excel(xlsx_path, sheet_name="Inventory_move")

    result = {
        "events_created": 0,
        "skipped": 0,
        "errors": [],
    }

    for _, row in df.iterrows():
        received_date = parse_date(row.get("Received_date"))
        internal_code = row.get("Internal_order_code")
        sku_key = str(row.get("SKU_key", "")).strip() if not pd.isna(row.get("SKU_key")) else None
        my_size = str(row.get("MY_SIZE", "")).strip() if not pd.isna(row.get("MY_SIZE")) else None
        qty = row.get("Truly_received", 0)

        if pd.isna(qty) or qty <= 0:
            result["skipped"] += 1
            continue

        if not sku_key or not my_size:
            result["skipped"] += 1
            continue

        qty = int(qty)
        sku_id = f"{sku_key}_{my_size}"

        if dry_run:
            result["events_created"] += 1
            continue

        try:
            # Check if INBOUND event already exists
            with get_db(db_path) as conn:
                existing = conn.execute("""
                    SELECT ledger_id FROM stock_ledger
                    WHERE sku_id = ? AND event_type = 'INBOUND'
                      AND reference_id = ? AND qty_change = ?
                """, (sku_id, internal_code, qty)).fetchone()

            if existing:
                result["skipped"] += 1
                continue

            add_ledger_event(
                event_type="INBOUND",
                sku_id=sku_id,
                qty_change=qty,
                event_date=received_date or date.today(),
                sku_key=sku_key,
                my_size=my_size,
                store_code="UNIVERSAL",
                reference_id=internal_code,
                reference_type="PO",
                notes=f"Imported from {Path(xlsx_path).name}",
                input_source="IMPORT",
                db_path=db_path,
            )
            result["events_created"] += 1

        except Exception as e:
            result["errors"].append(f"{sku_id}: {str(e)}")

    if verbose:
        print(f"  Inventory moves: {result['events_created']} events created, {result['skipped']} skipped")
        if result["errors"]:
            print(f"  Errors: {len(result['errors'])}")

    return result


def import_all(
    xlsx_path: str,
    skip_headers: bool = False,
    skip_lines: bool = False,
    skip_inventory: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
    db_path: Optional[Path] = None,
) -> dict:
    """
    Import all data from Excel file.

    Args:
        xlsx_path: Path to Excel file
        skip_headers: Skip PO headers
        skip_lines: Skip PO lines
        skip_inventory: Skip inventory movements
        dry_run: Simulate without changes
        verbose: Print progress
        db_path: Database path

    Returns:
        Dict with results from each step
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    results = {
        "file": Path(xlsx_path).name,
        "dry_run": dry_run,
    }

    if not skip_headers:
        if verbose:
            print("\n[1] Importing PO Headers...")
        results["headers"] = import_po_headers(xlsx_path, dry_run, verbose, db_path)

    if not skip_lines:
        if verbose:
            print("\n[2] Importing PO Lines...")
        results["lines"] = import_po_lines(xlsx_path, dry_run, verbose, db_path)

    if not skip_inventory:
        if verbose:
            print("\n[3] Importing Inventory Movements...")
        results["inventory"] = import_inventory_moves(xlsx_path, dry_run, verbose, db_path)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Import PO data from Inbound template Excel"
    )
    parser.add_argument(
        "file",
        type=str,
        help="Path to Excel file",
    )
    parser.add_argument(
        "--skip-headers",
        action="store_true",
        help="Skip PO headers import",
    )
    parser.add_argument(
        "--skip-lines",
        action="store_true",
        help="Skip PO lines import",
    )
    parser.add_argument(
        "--skip-inventory",
        action="store_true",
        help="Skip inventory movements import",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without saving",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"Error: File not found: {args.file}")
        return 1

    print("=" * 60)
    print(f"PO Import - {Path(args.file).name}")
    print("=" * 60)

    if args.dry_run:
        print("MODE: Dry Run (no changes will be saved)")

    results = import_all(
        xlsx_path=args.file,
        skip_headers=args.skip_headers,
        skip_lines=args.skip_lines,
        skip_inventory=args.skip_inventory,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("-" * 60)

    if "headers" in results:
        h = results["headers"]
        print(f"  PO Headers: {h.get('imported', 0)} new, {h.get('updated', 0)} updated")

    if "lines" in results:
        l = results["lines"]
        print(f"  PO Lines: {l.get('imported', 0)} new, {l.get('updated', 0)} updated")

    if "inventory" in results:
        i = results["inventory"]
        print(f"  Inventory: {i.get('events_created', 0)} INBOUND events")

    total_errors = sum(
        len(results.get(k, {}).get("errors", []))
        for k in ["headers", "lines", "inventory"]
    )
    print(f"  Errors: {total_errors}")
    print("=" * 60)

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
