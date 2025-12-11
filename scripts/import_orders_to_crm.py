#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 11: Import Kaspi ActiveOrders to CRM (xlwings version)

Uses xlwings to write to Excel, preserving formulas and external links.
Based on legacy ~/Docs/kaspi_etl/docs/ops/kaspi/import_active_orders.py

Usage:
    python scripts/import_orders_to_crm.py --verbose
    python scripts/import_orders_to_crm.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
from dateutil import parser as dtp

# xlwings for Excel-safe writing
import xlwings as xw

# openpyxl only for reading (inspection)
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string


# ---------- Configuration ----------

STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
}

DEFAULT_STATUS = 'Ожидает передачи курьеру'
DEFAULT_SIGNATURE = 'Не требуется'

# Canonical header mapping
CANON = {
    "order_id": ["№заказа", "номерзаказа", "orderid", "заказа"],  # заказа is normalized from "№ заказа"
    "status": ["статус"],
    "signature": ["требуетсяподписание"],
    "handover": ["плановаядатапередачикурьеру", "плановаядатапередачи"],
    "offer_name": ["названиетоваравkaspiмагазине"],
    "seller_name": ["названиевсистемепродавца"],
    "sku": ["артикул"],
    "warehouse": ["складпередачикд", "складпередачикурьерскойдоставки"],
    "phone": ["телефон", "phone", "cellphone"],
}


# ---------- Helpers ----------

def norm(s: str) -> str:
    """Normalize header for matching (lowercase, no punct, cyrillic-friendly)."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ё", "е")
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s", "", s)
    return s


def map_headers(df: pd.DataFrame) -> Dict[str, str]:
    """Return dict canonical_key -> actual df column name."""
    colmap = {}
    cols_norm = {norm(c): c for c in df.columns}
    for k, variants in CANON.items():
        for v in variants:
            v_norm = norm(v)
            if v_norm in cols_norm:
                colmap[k] = cols_norm[v_norm]
                break
    return colmap


def parse_kz_date(v) -> Optional[date]:
    """Parse various date formats from Kaspi exports."""
    if pd.isna(v):
        return None
    s = str(v).strip()
    try:
        d = dtp.parse(s, dayfirst=True, yearfirst=False).date()
        return d
    except Exception:
        try:
            if isinstance(v, pd.Timestamp):
                return v.date()
        except Exception:
            pass
        return None


def today_local() -> date:
    return datetime.now().date()


# ---------- Read & Filter ActiveOrders ----------

def find_active_orders(orders_dir: Path) -> List[Path]:
    """Find all ActiveOrders*.xlsx files in directory."""
    files = sorted([
        p for p in orders_dir.glob("*.xlsx") 
        if p.is_file() and not p.name.startswith("~$")
    ])
    return files


def read_active_orders(orders_dir: Path) -> Tuple[pd.DataFrame, List[Path]]:
    """Read all ActiveOrders files and concat."""
    files = find_active_orders(orders_dir)
    if not files:
        raise SystemExit(f"No .xlsx files found in {orders_dir}")
    
    frames = []
    for p in files:
        try:
            df = pd.read_excel(p, engine="openpyxl")
            df["__source_file__"] = p.name
            frames.append(df)
            print(f"  Read {p.name}: {len(df)} rows")
        except Exception as e:
            print(f"  WARN: cannot read {p.name}: {e}")
    
    if not frames:
        raise SystemExit("No valid Excel files found")
    
    return pd.concat(frames, ignore_index=True), files


def filter_for_shipping(
    df: pd.DataFrame, 
    status_wanted: str, 
    signature_wanted: Optional[str], 
    end_date: date
) -> Tuple[pd.DataFrame, Dict]:
    """Filter orders for shipping readiness."""
    colmap = map_headers(df)
    
    ok = pd.Series([True] * len(df))
    
    # Status filter
    if "status" in colmap:
        ok &= (df[colmap["status"]].astype(str).str.strip() == status_wanted)
    
    # Signature filter (exclude "Да" / "Требуется")
    if signature_wanted and "signature" in colmap:
        sig_col = df[colmap["signature"]].astype(str).str.strip().str.lower()
        ok &= ~sig_col.isin(['да', 'yes', 'true', '1', 'требуется'])
    
    # Date filter: planned_date <= end_date (None = unknown, include to be safe)
    if "handover" in colmap:
        handover = df[colmap["handover"]].apply(parse_kz_date)
        ok &= handover.apply(lambda d: d is None or d <= end_date)
    
    df_filtered = df[ok].copy()
    
    stats = {
        "files_seen": len(df["__source_file__"].unique()) if "__source_file__" in df else 0,
        "rows_in_files": int(len(df)),
        "rows_after_filters": int(len(df_filtered)),
        "target_end_date": end_date.isoformat(),
    }
    
    return df_filtered, stats


# ---------- CRM Inspection (openpyxl read-only) ----------

def inspect_crm_sheet(
    crm_path: Path,
    sheet_name: str,
    table_name: str
) -> Tuple[int, Optional[int], int, int, List[str]]:
    """
    Inspect CRM to find column positions.

    CRM structure:
    - Column B (2): Date - we write here
    - Column I (9): Phone - we write here (Phase 12)
    - Columns A-X: Formula columns (auto-calculate)
    - Columns Y-AZ (25-52): Raw Kaspi data - we write here

    Returns: (date_col, phone_col, start_col, end_col, slice_headers)
    """
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    if sheet_name not in wb.sheetnames:
        raise SystemExit(f'Sheet "{sheet_name}" not found in {crm_path}')

    ws = wb[sheet_name]
    header_vals = [c.value if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]

    idx_date = None
    idx_phone = None  # Phone column (column I)
    idx_start = None  # Raw Kaspi start (№ заказа in column Y)
    idx_end = None    # Raw Kaspi end (Склад передачи КД in column AZ)

    for i, h in enumerate(header_vals, start=1):
        hnorm = norm(h)
        if idx_date is None and hnorm in {"date", "дата"}:
            idx_date = i
        # Phone column (column I in CRM)
        if idx_phone is None and hnorm in {"phone", "телефон", "cellphone"}:
            idx_phone = i
        # Look for raw Kaspi columns (Russian headers starting at Y)
        # Note: "№ заказа" normalizes to "заказа" (№ symbol stripped)
        if idx_start is None and hnorm in {"№заказа", "номерзаказа", "заказа"}:
            idx_start = i
        if hnorm in {"складпередачикд", "складпередачикурьерскойдоставки"}:
            idx_end = i  # Keep updating to get the last one

    if idx_date is None:
        raise SystemExit(f"Could not find 'Date' column. Headers: {header_vals[:10]}...")

    if idx_start is None or idx_end is None or idx_end < idx_start:
        raise SystemExit(
            f"Could not locate raw Kaspi columns (Y-AZ). Need '№ заказа' and 'Склад передачи КД'. "
            f"Headers at positions 25-30: {header_vals[24:30] if len(header_vals) >= 30 else 'N/A'}"
        )

    slice_headers = [header_vals[j-1] for j in range(idx_start, idx_end + 1)]
    wb.close()

    print(f"  Date column: {idx_date} (B)")
    if idx_phone:
        print(f"  Phone column: {idx_phone} (I)")
    else:
        print(f"  Phone column: not found (will skip phone import)")
    print(f"  Raw Kaspi columns: {idx_start}-{idx_end} (Y-AZ)")

    return idx_date, idx_phone, idx_start, idx_end, slice_headers


def _resolve_table(ws, table_name: str):
    """Find table in worksheet."""
    tables = ws.tables
    if table_name in tables:
        return tables[table_name]
    if tables:
        return next(iter(tables.values()))
    raise RuntimeError(f"No tables found on sheet {ws.title}")


def _table_bounds(table) -> Tuple[int, int, int, int]:
    """Get table bounds: (start_col, start_row, end_col, end_row)."""
    start_ref, end_ref = table.ref.split(':')
    start_col_letters, start_row = coordinate_from_string(start_ref)
    end_col_letters, end_row = coordinate_from_string(end_ref)
    start_col = column_index_from_string(start_col_letters)
    end_col = column_index_from_string(end_col_letters)
    return start_col, start_row, end_col, end_row


def collect_existing_order_ids(
    crm_path: Path, 
    sheet_name: str, 
    table_name: str, 
    order_col_abs: int
) -> set:
    """Get set of existing OrderIDs from CRM."""
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)
        
        if not (start_col <= order_col_abs <= end_col):
            return set()
        
        order_ids = set()
        for row in ws.iter_rows(min_row=start_row + 1, max_row=end_row, 
                                min_col=order_col_abs, max_col=order_col_abs):
            cell = row[0]
            val = cell.value
            if val in (None, ""):
                continue
            if isinstance(val, str) and val.startswith("="):
                continue
            order_ids.add(str(val).strip())
        return order_ids
    finally:
        wb.close()


# ---------- Build Staging Data ----------

def build_staging(df_filt: pd.DataFrame, crm_slice_headers: List[str]) -> Tuple[List[List], List[str]]:
    """
    Build 2D list matching CRM slice columns plus phone values.

    Returns: (stage_block, phone_values)
    """
    colmap = map_headers(df_filt)

    # Series by canonical key
    S: Dict[str, pd.Series] = {}
    for k, real in colmap.items():
        S[k] = df_filt[real].astype(object)

    # Direct lookup by normalized header
    cols_norm_map = {norm(col): df_filt[col].astype(object) for col in df_filt.columns}

    n = len(df_filt)

    def col_for(header_text: str) -> pd.Series:
        h = norm(header_text)

        # Map canonical keys
        # Note: "№ заказа" normalizes to "заказа"
        if h in {"orderid", "номерзаказа", "заказ", "№заказа", "заказа"} and "order_id" in S:
            col = S["order_id"].copy()
            col = col.apply(lambda v: "" if pd.isna(v) else (
                str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v)
            ))
            return col

        if h in {"названиевсистемепродавца"} and "seller_name" in S:
            return S["seller_name"]

        if h in {"названиетоваравkaspiмагазине"} and "offer_name" in S:
            return S["offer_name"]

        if h in {"артикул"} and "sku" in S:
            return S["sku"]

        if h in {"складпередачикд", "складпередачикурьерскойдоставки"} and "warehouse" in S:
            return S["warehouse"]

        # Direct match
        if h in cols_norm_map:
            return cols_norm_map[h]

        return pd.Series([""] * n, index=df_filt.index, dtype=object)

    cols = [col_for(h) for h in crm_slice_headers]

    stage = []
    for i in range(len(df_filt)):
        row = []
        for s in cols:
            v = s.iloc[i]
            if pd.isna(v):
                v = ""
            row.append(v)
        stage.append(row)

    # Extract phone values separately (Phase 12)
    phone_values = []
    if "phone" in S:
        for i in range(len(df_filt)):
            v = S["phone"].iloc[i]
            if pd.isna(v):
                v = ""
            else:
                v = str(v).strip()
            phone_values.append(v)
    else:
        phone_values = [""] * len(df_filt)

    return stage, phone_values


# ---------- Excel Append via xlwings ----------

def excel_append_xlwings(
    out_wb: Path,
    sheet_name: str,
    table_name: str,
    date_col_abs: int,
    phone_col_abs: Optional[int],
    start_col_abs: int,
    end_col_abs: int,
    stage_block: List[List],
    phone_values: List[str],
    set_date: date,
    slice_headers: List[str]
) -> None:
    """
    Append rows to CRM using xlwings (preserves formulas & external links).

    Args:
        phone_col_abs: Column for phone data (column I), or None to skip
        phone_values: List of phone strings to write
    """
    n = len(stage_block)
    if n == 0:
        return

    print(f"  Opening Excel (hidden)...")
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(out_wb))
        sh = wb.sheets[sheet_name]

        # Find the table
        try:
            tbl = sh.tables[table_name]
        except KeyError:
            tables = list(sh.tables)
            if not tables:
                raise RuntimeError(f"No table found on sheet {sheet_name}")
            tbl = tables[0]

        # Calculate where new rows go
        total_rows_before = tbl.range.rows.count
        header_row = tbl.range.row
        data_rows_before = total_rows_before - 1

        top_row = header_row + data_rows_before + 1
        bottom_row = top_row + n - 1

        print(f"  Appending {n} rows starting at row {top_row}")

        # Write date column
        date_vals = [[set_date] for _ in range(n)]
        date_range = sh.range((top_row, date_col_abs), (bottom_row, date_col_abs))
        date_range.value = date_vals
        date_range.number_format = "dd.mm.yyyy"

        # Write phone column (Phase 12)
        if phone_col_abs and phone_values:
            # Only write non-empty phone values
            has_phones = any(v for v in phone_values)
            if has_phones:
                phone_range = sh.range((top_row, phone_col_abs), (bottom_row, phone_col_abs))
                phone_range.value = [[v] for v in phone_values]
                print(f"  Phone data written to column {phone_col_abs}")

        # Write data columns (skip formula-driven columns like OrderID if they exist in table)
        width = len(slice_headers)
        for offset in range(width):
            header = slice_headers[offset]
            col_values = [row[offset] for row in stage_block]

            # Skip entirely empty columns
            if all((v is None) or (isinstance(v, str) and v == "") for v in col_values):
                continue

            target = sh.range((top_row, start_col_abs + offset), (bottom_row, start_col_abs + offset))
            target.value = [[v] for v in col_values]

        wb.save()
        wb.close()
        print(f"  ✅ Saved {out_wb.name}")

    finally:
        app.quit()


# ---------- Archive Source Files ----------

def archive_run(orders_dir: Path, source_files: List[Path], df_filt: pd.DataFrame) -> Path:
    """Archive source files and create log."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = orders_dir / "archive_orders"
    archive_root.mkdir(parents=True, exist_ok=True)
    
    run_dir = archive_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Move source files
    for src in source_files:
        dest = run_dir / src.name
        try:
            shutil.move(str(src), str(dest))
            print(f"  Archived: {src.name}")
        except Exception as e:
            print(f"  WARN: could not archive {src.name}: {e}")
    
    # Create log CSV
    colmap = map_headers(df_filt)
    log_cols = []
    for key in ("order_id", "handover", "warehouse", "status"):
        if key in colmap:
            log_cols.append(colmap[key])
    
    if "__source_file__" in df_filt.columns:
        log_cols.append("__source_file__")
    
    if log_cols:
        df_log = df_filt[log_cols].copy()
        rename_map = {colmap[k]: k for k in colmap if colmap[k] in log_cols}
        df_log = df_log.rename(columns=rename_map)
        
        log_path = run_dir / "appended_orders.csv"
        df_log.to_csv(log_path, index=False)
    
    return run_dir


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(
        description="Import Kaspi ActiveOrders to CRM (xlwings, Excel-safe)"
    )
    parser.add_argument(
        "--orders-dir", 
        type=Path, 
        default=Path("excel_ui/ActiveOrders"),
        help="Directory containing ActiveOrders*.xlsx"
    )
    parser.add_argument(
        "--crm-file", 
        type=Path, 
        default=Path("excel_ui/SALES_KSP_CRM_V3.xlsx"),
        help="CRM Excel file"
    )
    parser.add_argument(
        "--sheet", 
        default="SALES_KSP_CRM_1",
        help="CRM sheet name"
    )
    parser.add_argument(
        "--table", 
        default="tb_SalesRaw",
        help="CRM table name"
    )
    parser.add_argument(
        "--date-end", 
        default="tomorrow",
        help="Upper bound for planned date (today, tomorrow, or YYYY-MM-DD)"
    )
    parser.add_argument(
        "--append-date", 
        default="today",
        help="Date to stamp into CRM Date column"
    )
    parser.add_argument(
        "--status", 
        default=DEFAULT_STATUS,
        help="Status filter"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Preview only, don't write to Excel"
    )
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Parse dates
    if args.date_end.lower() == "today":
        end_date = today_local()
    elif args.date_end.lower() == "tomorrow":
        end_date = today_local() + timedelta(days=1)
    else:
        end_date = dtp.parse(args.date_end).date()
    
    if args.append_date.lower() == "today":
        append_date = today_local()
    else:
        append_date = dtp.parse(args.append_date).date()
    
    print("=" * 60)
    print("  Kaspi Order Import (xlwings)")
    print("=" * 60)
    print(f"  Orders dir: {args.orders_dir}")
    print(f"  CRM file: {args.crm_file}")
    print(f"  Date filter: <= {end_date}")
    print(f"  Append date: {append_date}")
    print()
    
    # Read and filter
    df_all, source_files = read_active_orders(args.orders_dir)
    df_filt, stats = filter_for_shipping(df_all, args.status, None, end_date)
    
    print(f"\nFiltered: {stats['rows_in_files']} → {stats['rows_after_filters']} rows")
    
    if df_filt.empty:
        print("No orders match filters. Nothing to import.")
        return
    
    # Inspect CRM structure
    date_abs, phone_abs, start_abs, end_abs, slice_headers = inspect_crm_sheet(
        args.crm_file, args.sheet, args.table
    )
    
    # Get existing order IDs for dedup
    existing_ids = collect_existing_order_ids(args.crm_file, args.sheet, args.table, start_abs)
    print(f"Existing orders in CRM: {len(existing_ids)}")
    
    # Build staging data (returns tuple: stage_block, phone_values)
    stage, phone_values = build_staging(df_filt, slice_headers)

    # Dedup against existing
    colmap = map_headers(df_filt)
    if "order_id" in colmap:
        order_col = colmap["order_id"]
        df_filt["_oid"] = df_filt[order_col].astype(str)
        new_mask = ~df_filt["_oid"].isin(existing_ids)

        # Filter stage and phone values to match
        indices_to_keep = df_filt[new_mask].index.tolist()
        stage_filtered = [stage[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]
        phone_filtered = [phone_values[i] for i, idx in enumerate(df_filt.index) if idx in indices_to_keep]

        dup_count = len(stage) - len(stage_filtered)
        if dup_count > 0:
            print(f"Skipped {dup_count} duplicates (already in CRM)")

        stage = stage_filtered
        phone_values = phone_filtered

    print(f"\nOrders to append: {len(stage)}")
    
    if len(stage) == 0:
        print("All orders already in CRM. Nothing to import.")
        return
    
    if args.dry_run:
        print("\n[DRY RUN] Would append but skipping.")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return
    
    # Append via xlwings
    excel_append_xlwings(
        args.crm_file,
        args.sheet,
        args.table,
        date_abs,
        phone_abs,
        start_abs,
        end_abs,
        stage,
        phone_values,
        append_date,
        slice_headers
    )
    
    # Archive source files
    archive_path = archive_run(args.orders_dir, source_files, df_filt)
    
    print(f"\n✅ Import complete!")
    print(f"   Appended: {len(stage)} orders")
    print(f"   Archived: {archive_path}")


if __name__ == "__main__":
    main()
