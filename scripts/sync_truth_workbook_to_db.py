#!/usr/bin/env python3
"""
Sync truth sheets from Inventory_Core workbook to database.

This script ingests ONLY the canonical truth sheets from the workbook:
- Dim_Params
- Dim_Params_PT
- DIM_SKU_ID
- Dim_SKU
- SizeMix_and_Di_Anchor
- Fact_Sales
- Fact_PO_Lines
- Dim_PO_Header

Usage:
    python scripts/sync_truth_workbook_to_db.py
    python scripts/sync_truth_workbook_to_db.py --workbook /path/to/Inventory_Core_V18.xlsx
    python scripts/sync_truth_workbook_to_db.py --dry-run
    python scripts/sync_truth_workbook_to_db.py --snapshot-date 2025-12-21
"""

import argparse
import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any

import openpyxl

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Default paths
DEFAULT_WORKBOOK = PROJECT_ROOT / "excel" / "Inventory_Core_V18.xlsx"
DB_PATH = PROJECT_ROOT / "db" / "app.db"

# Truth sheets to ingest (per plan.md)
TRUTH_SHEETS = [
    "Dim_Params",
    "Dim_Params_PT",
    "DIM_SKU_ID",
    "Dim_SKU",
    "SizeMix_and_Di_Anchor",
    "Fact_Sales",
    "Fact_PO_Lines",
    "Dim_PO_Header",
]


def parse_date(val: Any) -> Optional[str]:
    """Convert Excel date to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, str):
        # Try common formats
        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"]:
            try:
                return datetime.strptime(val, fmt).date().isoformat()
            except ValueError:
                continue
        return val  # Return as-is if parsing fails
    return str(val)


def parse_bool(val: Any) -> int:
    """Convert Excel boolean to SQLite integer."""
    if val is None:
        return 0
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return 1 if val else 0
    if isinstance(val, str):
        return 1 if val.lower() in ("true", "yes", "1") else 0
    return 0


def parse_float(val: Any, default: float = 0.0) -> float:
    """Parse float value with fallback."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def parse_int(val: Any, default: int = 0) -> int:
    """Parse integer value with fallback."""
    if val is None:
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def read_sheet_as_dicts(wb, sheet_name: str) -> list[dict]:
    """Read worksheet into list of dicts keyed by header row."""
    if sheet_name not in wb.sheetnames:
        print(f"  WARNING: Sheet '{sheet_name}' not found in workbook")
        return []

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # First row is header
    headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(rows[0])]

    result = []
    for row in rows[1:]:
        if not row or all(v is None for v in row):
            continue  # Skip empty rows
        record = dict(zip(headers, row))
        result.append(record)

    return result


def sync_dim_params(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync dim_params table (global parameters)."""
    count = 0
    for rec in records:
        param = rec.get("Param")
        value = parse_float(rec.get("Value"), 0.0)
        notes = rec.get("Notes") or ""

        if not param:
            continue

        if dry_run:
            print(f"    [DRY] dim_params: {param} = {value}")
            count += 1
            continue

        conn.execute("""
            INSERT OR REPLACE INTO dim_params (param_key, product_type, param_value, description)
            VALUES (?, NULL, ?, ?)
        """, (param, value, notes))
        count += 1

    return count


def sync_dim_params_pt(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync product-type specific parameters into dim_params."""
    count = 0
    for rec in records:
        product_type = rec.get("Product_Type")
        if not product_type:
            continue

        # Map columns to param keys
        param_map = {
            "R_days": "R_days",
            "L_days": "L_days",
            "B_days": "B_days",
            "z_factor": "z_factor",
            "TV_mix": "TV_mix",
            "VAT_rate": "VAT_rate",
            "Platform_fee": "Platform_fee_pct",
            "Payout_lag": "Payout_lag_days",
        }

        for col, param_key in param_map.items():
            value = parse_float(rec.get(col), None)
            if value is None:
                continue

            full_key = f"{param_key}_{product_type}"

            if dry_run:
                print(f"    [DRY] dim_params: {full_key} = {value}")
                count += 1
                continue

            conn.execute("""
                INSERT OR REPLACE INTO dim_params (param_key, product_type, param_value, description)
                VALUES (?, ?, ?, ?)
            """, (full_key, product_type, value, f"From Dim_Params_PT"))
            count += 1

    return count


def sync_dim_sku(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync dim_sku table (style-level SKU master)."""
    count = 0
    for rec in records:
        sku_key = rec.get("SKU_key")
        if not sku_key:
            continue

        product_type = rec.get("Product_Type") or "CL"
        weight_kg = parse_float(rec.get("Weight_kg"), 0.5)
        base_cost_cny = parse_float(rec.get("BaseCost_CNY"), 50.0)
        is_active = parse_bool(rec.get("Is_Active"))

        # Extract model/color from sku_key (e.g., CL_OC_MEN_LINE52_BLACK)
        parts = sku_key.split("_")
        model = parts[-2] if len(parts) >= 2 else sku_key
        color = parts[-1] if len(parts) >= 1 else "UNKNOWN"

        if dry_run:
            print(f"    [DRY] dim_sku: {sku_key} ({product_type})")
            count += 1
            continue

        conn.execute("""
            INSERT OR REPLACE INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny, weight_kg, active_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sku_key, model, color, product_type, base_cost_cny, weight_kg, is_active))
        count += 1

    return count


def sync_dim_sku_size(
    conn,
    records: list[dict],
    snapshot_date: str,
    dry_run: bool = False
) -> tuple[int, int]:
    """
    Sync DIM_SKU_ID sheet to dim_sku_size and fact_inventory_snapshot_size.

    Returns: (sku_size_count, snapshot_count)
    """
    sku_size_count = 0
    snapshot_count = 0

    for rec in records:
        sku_id = rec.get("SKU_ID")
        sku_key = rec.get("SKU_key")
        my_size = rec.get("MY_SIZE")

        if not sku_id or not sku_key or not my_size:
            continue

        # Get stock values
        current_stock = parse_int(rec.get("Current_stock"), 0)
        inbound_stock = parse_int(rec.get("Inbound_stock"), 0)

        # Determine snapshot date from workbook or override
        stock_date_col = rec.get("Current_stock_Stock_date")
        if stock_date_col:
            ws_snapshot_date = parse_date(stock_date_col) or snapshot_date
        else:
            ws_snapshot_date = snapshot_date

        if dry_run:
            print(f"    [DRY] dim_sku_size: {sku_id} ({my_size})")
            print(f"    [DRY] fact_inventory_snapshot_size: {sku_id} @ {ws_snapshot_date} = {current_stock}")
            sku_size_count += 1
            snapshot_count += 1
            continue

        # Upsert dim_sku_size
        conn.execute("""
            INSERT OR REPLACE INTO dim_sku_size (
                sku_id, sku_key, my_size, active_flag
            ) VALUES (?, ?, ?, 1)
        """, (sku_id, sku_key, my_size))
        sku_size_count += 1

        # Upsert fact_inventory_snapshot_size
        conn.execute("""
            INSERT OR REPLACE INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (ws_snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock))
        snapshot_count += 1

    return sku_size_count, snapshot_count


def sync_fact_sales(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync Fact_Sales sheet to fact_sales table."""
    count = 0
    for rec in records:
        order_id = rec.get("OrderID")
        order_date = parse_date(rec.get("Date"))
        sku_key = rec.get("SKU_key")
        sku_id = rec.get("SKU_ID")
        kaspi_offer_name = rec.get("Kaspi_Offer_name") or ""

        if not order_id or not order_date or not sku_key:
            continue

        quantity = parse_int(rec.get("Quantity"), 1)
        sell_price = parse_float(rec.get("Sell_price_kzt"), 0.0)
        product_type = rec.get("Product_Type") or "CL"
        channel = rec.get("Channel") or "Kaspi"

        # Get calculated fields from workbook
        delivery_fee = parse_float(rec.get("Delivery_fee"), 0.0)
        net_rev_unit = parse_float(rec.get("Net_rev_unit"), 0.0)
        line_net_rev = parse_float(rec.get("Line_NetRev"), 0.0)
        cogs_unit = parse_float(rec.get("COGS_unit"), 0.0)
        cogs_line = parse_float(rec.get("COGS_line"), 0.0)
        profit_unit = parse_float(rec.get("Profit_unit"), 0.0)
        profit_line = parse_float(rec.get("Profit_line"), 0.0)

        # Extract my_size from sku_id (last part after underscore)
        my_size = sku_id.split("_")[-1] if sku_id else None

        if dry_run:
            print(f"    [DRY] fact_sales: {order_id} {sku_key} x{quantity} @ {order_date}")
            count += 1
            continue

        try:
            conn.execute("""
                INSERT OR REPLACE INTO fact_sales (
                    order_id, kaspi_offer_name, store_code, order_date, sku_key, sku_id,
                    my_size, quantity, sell_price_kzt, product_type, channel,
                    delivery_fee, net_rev_unit, line_net_rev, cogs_unit, cogs_line,
                    profit_unit, profit_line
                ) VALUES (?, ?, 'UNIVERSAL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(order_id), kaspi_offer_name, order_date, sku_key, sku_id,
                my_size, quantity, sell_price, product_type, channel,
                delivery_fee, net_rev_unit, line_net_rev, cogs_unit, cogs_line,
                profit_unit, profit_line
            ))
            count += 1
        except sqlite3.IntegrityError as e:
            # Skip duplicates
            pass

    return count


def sync_dim_anchor(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync SizeMix_and_Di_Anchor to dim_anchor table."""
    # First, ensure the dim_anchor table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dim_anchor (
            sku_key TEXT PRIMARY KEY,
            d_active REAL,
            sigma REAL,
            S_share REAL, M_share REAL, L_share REAL, XL_share REAL,
            _2XL_share REAL, _3XL_share REAL, _4XL_share REAL,
            S_D REAL, M_D REAL, L_D REAL, XL_D REAL,
            _2XL_D REAL, _3XL_D REAL, _4XL_D REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    count = 0
    for rec in records:
        sku_key = rec.get("SKU_key")
        if not sku_key:
            continue

        d_active = parse_float(rec.get("D_active"), 0.0)

        if dry_run:
            print(f"    [DRY] dim_anchor: {sku_key} D_active={d_active:.2f}")
            count += 1
            continue

        # Parse size shares and demands
        s_share = parse_float(rec.get("S_share"), 0.0)
        m_share = parse_float(rec.get("M_share"), 0.0)
        l_share = parse_float(rec.get("L_share"), 0.0)
        xl_share = parse_float(rec.get("XL_share"), 0.0)
        _2xl_share = parse_float(rec.get("2XL_share"), 0.0)
        _3xl_share = parse_float(rec.get("3XL_share"), 0.0)
        _4xl_share = parse_float(rec.get("4XL_share"), 0.0)

        s_d = parse_float(rec.get("S_D"), 0.0)
        m_d = parse_float(rec.get("M_D"), 0.0)
        l_d = parse_float(rec.get("L_D"), 0.0)
        xl_d = parse_float(rec.get("XL_D"), 0.0)
        _2xl_d = parse_float(rec.get("2XL_D"), 0.0)
        _3xl_d = parse_float(rec.get("3XL_D"), 0.0)
        _4xl_d = parse_float(rec.get("4XL_D"), 0.0)

        conn.execute("""
            INSERT OR REPLACE INTO dim_anchor (
                sku_key, d_active, sigma,
                S_share, M_share, L_share, XL_share, _2XL_share, _3XL_share, _4XL_share,
                S_D, M_D, L_D, XL_D, _2XL_D, _3XL_D, _4XL_D
            ) VALUES (?, ?, 0.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sku_key, d_active,
            s_share, m_share, l_share, xl_share, _2xl_share, _3xl_share, _4xl_share,
            s_d, m_d, l_d, xl_d, _2xl_d, _3xl_d, _4xl_d
        ))
        count += 1

    return count


def sync_po_header(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync Dim_PO_Header to po_header table."""
    # Ensure table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS po_header (
            internal_order_code TEXT PRIMARY KEY,
            brand TEXT,
            product_type TEXT,
            vendor_id TEXT,
            message_date TEXT,
            po_date TEXT,
            ship_date_cargo TEXT,
            est_arrival_date TEXT,
            actual_arrival_date TEXT,
            fx_cny_kzt REAL,
            status TEXT,
            is_paid TEXT,
            total_qty INTEGER,
            total_cost_cny REAL,
            total_cost_kzt REAL,
            total_weight_kg REAL,
            freight_cost_usd REAL,
            freight_cost_kzt REAL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    count = 0
    for rec in records:
        internal_code = rec.get("Internal_order_code")
        if not internal_code:
            continue

        if dry_run:
            print(f"    [DRY] po_header: {internal_code}")
            count += 1
            continue

        conn.execute("""
            INSERT OR REPLACE INTO po_header (
                internal_order_code, brand, product_type, vendor_id,
                message_date, po_date, ship_date_cargo, est_arrival_date, actual_arrival_date,
                fx_cny_kzt, status, is_paid, total_qty, total_cost_cny, total_cost_kzt,
                total_weight_kg, freight_cost_usd, freight_cost_kzt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            internal_code,
            rec.get("Brand"),
            rec.get("Product_Type"),
            rec.get("VendorID"),
            parse_date(rec.get("Message_date")),
            parse_date(rec.get("PO_Date")),
            parse_date(rec.get("Ship_Date_Cargo")),
            parse_date(rec.get("Est_arrival_date")),
            parse_date(rec.get("Actual_arrival_date")),
            parse_float(rec.get("FX_CNYKZT"), 78.0),
            rec.get("Status") or "UNKNOWN",
            rec.get("IS_PAID") or "NO",
            parse_int(rec.get("Total_qty"), 0),
            parse_float(rec.get("Total_cost_CNY"), 0.0),
            parse_float(rec.get("Total_cost_KZT"), 0.0),
            parse_float(rec.get("Total_weight_kg"), 0.0),
            parse_float(rec.get("Freight_cost_USD"), 0.0),
            parse_float(rec.get("Freight_cost_KZT"), 0.0),
        ))
        count += 1

    return count


def sync_po_lines(conn, records: list[dict], dry_run: bool = False) -> int:
    """Sync Fact_PO_Lines to fact_po_lines table."""
    count = 0
    for rec in records:
        internal_code = rec.get("Internal_order_code")
        sku_key = rec.get("SKU_KEY")
        sku_id = rec.get("SKU_ID")
        my_size = rec.get("MY_SIZE")

        if not internal_code or not sku_key:
            continue

        order_qty = parse_int(rec.get("Order_Quantity"), 0)
        received_qty = parse_int(rec.get("Received_Qty"), 0)
        unit_cost = parse_float(rec.get("UnitCost_CNY"), 0.0)
        status = rec.get("Status") or "UNKNOWN"

        if dry_run:
            print(f"    [DRY] fact_po_lines: {internal_code} {sku_id} x{order_qty}")
            count += 1
            continue

        try:
            conn.execute("""
                INSERT OR REPLACE INTO fact_po_lines (
                    po_id, store_code, sku_key, sku_id, my_size,
                    order_quantity, unit_cost_kzt, received_qty, status
                ) VALUES (?, 'UNIVERSAL', ?, ?, ?, ?, ?, ?, ?)
            """, (
                internal_code, sku_key, sku_id or f"{sku_key}_{my_size}", my_size,
                order_qty, unit_cost * 78,  # Convert CNY to KZT
                received_qty, status
            ))
            count += 1
        except sqlite3.IntegrityError:
            pass

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Sync truth sheets from Inventory_Core workbook to database"
    )
    parser.add_argument(
        "--workbook", "-w",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help=f"Path to Inventory_Core workbook (default: {DEFAULT_WORKBOOK})"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to SQLite database (default: {DB_PATH})"
    )
    parser.add_argument(
        "--snapshot-date",
        type=str,
        default=None,
        help="Override stock snapshot date (ISO format: YYYY-MM-DD)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only, don't write to DB"
    )
    parser.add_argument(
        "--sheets",
        type=str,
        default=None,
        help="Comma-separated list of sheets to sync (default: all truth sheets)"
    )
    args = parser.parse_args()

    # Validate workbook path
    if not args.workbook.exists():
        print(f"ERROR: Workbook not found: {args.workbook}")
        sys.exit(1)

    print("=" * 60)
    print(f"Sync Truth Workbook to DB: {datetime.now().isoformat()}")
    print("=" * 60)
    print(f"Workbook: {args.workbook}")
    print(f"Database: {args.db}")
    if args.snapshot_date:
        print(f"Snapshot date override: {args.snapshot_date}")
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    # Load workbook
    print("Loading workbook...")
    wb = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    print(f"  Sheets found: {wb.sheetnames}")

    # Filter to requested sheets
    if args.sheets:
        sheets_to_sync = [s.strip() for s in args.sheets.split(",")]
    else:
        sheets_to_sync = TRUTH_SHEETS

    print(f"  Syncing: {sheets_to_sync}")
    print()

    # Get or determine snapshot date
    if args.snapshot_date:
        snapshot_date = args.snapshot_date
    else:
        # Try to get from DIM_SKU_ID first row
        dim_sku_id = read_sheet_as_dicts(wb, "DIM_SKU_ID")
        if dim_sku_id and dim_sku_id[0].get("Current_stock_Stock_date"):
            snapshot_date = parse_date(dim_sku_id[0]["Current_stock_Stock_date"])
        else:
            snapshot_date = date.today().isoformat()
    print(f"Stock snapshot date: {snapshot_date}")
    print()

    # Connect to database
    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row

    results = {}

    try:
        # Sync each sheet
        if "Dim_Params" in sheets_to_sync:
            print("Syncing Dim_Params...")
            records = read_sheet_as_dicts(wb, "Dim_Params")
            count = sync_dim_params(conn, records, args.dry_run)
            results["dim_params"] = count
            print(f"  -> {count} parameters")

        if "Dim_Params_PT" in sheets_to_sync:
            print("Syncing Dim_Params_PT...")
            records = read_sheet_as_dicts(wb, "Dim_Params_PT")
            count = sync_dim_params_pt(conn, records, args.dry_run)
            results["dim_params_pt"] = count
            print(f"  -> {count} product-type parameters")

        if "Dim_SKU" in sheets_to_sync:
            print("Syncing Dim_SKU...")
            records = read_sheet_as_dicts(wb, "Dim_SKU")
            count = sync_dim_sku(conn, records, args.dry_run)
            results["dim_sku"] = count
            print(f"  -> {count} SKUs")

        if "DIM_SKU_ID" in sheets_to_sync:
            print("Syncing DIM_SKU_ID (sizes + inventory snapshot)...")
            records = read_sheet_as_dicts(wb, "DIM_SKU_ID")
            sku_size_count, snapshot_count = sync_dim_sku_size(
                conn, records, snapshot_date, args.dry_run
            )
            results["dim_sku_size"] = sku_size_count
            results["fact_inventory_snapshot_size"] = snapshot_count
            print(f"  -> {sku_size_count} size records, {snapshot_count} stock snapshots")

        if "SizeMix_and_Di_Anchor" in sheets_to_sync:
            print("Syncing SizeMix_and_Di_Anchor (dim_anchor)...")
            records = read_sheet_as_dicts(wb, "SizeMix_and_Di_Anchor")
            count = sync_dim_anchor(conn, records, args.dry_run)
            results["dim_anchor"] = count
            print(f"  -> {count} anchor records")

        if "Fact_Sales" in sheets_to_sync:
            print("Syncing Fact_Sales...")
            records = read_sheet_as_dicts(wb, "Fact_Sales")
            count = sync_fact_sales(conn, records, args.dry_run)
            results["fact_sales"] = count
            print(f"  -> {count} sales records")

        if "Dim_PO_Header" in sheets_to_sync:
            print("Syncing Dim_PO_Header (po_header)...")
            records = read_sheet_as_dicts(wb, "Dim_PO_Header")
            count = sync_po_header(conn, records, args.dry_run)
            results["po_header"] = count
            print(f"  -> {count} PO headers")

        if "Fact_PO_Lines" in sheets_to_sync:
            print("Syncing Fact_PO_Lines...")
            records = read_sheet_as_dicts(wb, "Fact_PO_Lines")
            count = sync_po_lines(conn, records, args.dry_run)
            results["fact_po_lines"] = count
            print(f"  -> {count} PO lines")

        if not args.dry_run:
            conn.commit()
            print("\nChanges committed to database.")

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
        wb.close()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for table, count in results.items():
        print(f"  {table}: {count} records")

    # Print sanity checks
    print("\nSanity check queries to run:")
    print(f"  sqlite3 {args.db} \"SELECT COUNT(*) FROM fact_sales WHERE order_date = (SELECT MAX(order_date) FROM fact_sales);\"")
    print(f"  sqlite3 {args.db} \"SELECT snapshot_date, COUNT(*), SUM(current_stock) FROM fact_inventory_snapshot_size GROUP BY snapshot_date;\"")
    print(f"  sqlite3 {args.db} \"SELECT COUNT(*) FROM dim_anchor WHERE d_active > 0;\"")


if __name__ == "__main__":
    main()
