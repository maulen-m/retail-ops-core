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

# xlwings for Excel-safe writing (optional at import time)
try:
    import xlwings as xw
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    xw = None

# openpyxl only for reading (inspection)
from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path, get_data_root


# ---------- CRM Backup ----------

def backup_crm(crm_path: Path) -> Path:
    """
    Create timestamped backup of CRM file before import.

    Stores backups in excel_ui/backups/, keeps last 7 days.

    Returns:
        Path to backup file
    """
    backup_dir = crm_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"CRM_backup_{timestamp}.xlsx"

    # Create backup
    shutil.copy2(crm_path, backup_path)

    # Cleanup: keep last 7 days only
    cutoff = datetime.now() - timedelta(days=7)
    for old_backup in backup_dir.glob("CRM_backup_*.xlsx"):
        try:
            # Parse timestamp from filename: CRM_backup_YYYYMMDD_HHMMSS.xlsx
            ts_str = old_backup.stem.replace("CRM_backup_", "")
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if ts < cutoff:
                old_backup.unlink()
        except (ValueError, OSError):
            pass  # Skip files that don't match pattern

    return backup_path


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
    "status_change_date": ["датаизменениястатуса"],  # Phase 12 Part 6: status change timestamp
    "signature": ["требуетсяподписание"],
    "handover": ["плановаядатапередачикурьеру", "плановаядатапередачи"],
    "offer_name": ["названиетоваравkaspiмагазине"],
    "seller_name": ["названиевсистемепродавца"],
    "sku": ["артикул"],
    "warehouse": ["складпередачикд", "складпередачикурьерскойдоставки"],
    "phone": ["телефон", "phone", "cellphone"],
    "quantity": ["количество", "qty", "quantity"],
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
    
    # Date filter: planned_date == end_date (exact match for TODAY only)
    # Phase 12 Part 3: Changed from <= to == for TODAY-only filtering
    if "handover" in colmap:
        handover = df[colmap["handover"]].apply(parse_kz_date)
        ok &= handover.apply(lambda d: d is not None and d == end_date)
    
    df_filtered = df[ok].copy()
    
    stats = {
        "files_seen": len(df["__source_file__"].unique()) if "__source_file__" in df else 0,
        "rows_in_files": int(len(df)),
        "rows_after_filters": int(len(df_filtered)),
        "target_end_date": end_date.isoformat(),
    }
    
    return df_filtered, stats


def sort_for_crm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort dataframe for CRM append order.

    Sort order (Phase 12 Part 6 - Updated):
    1. Status (cancelled/returned on top) - problematic orders first
    2. STORE_NAME / warehouse (ascending) - group by store for visual clarity
    3. OrderID (ascending) - group same orders together
    4. Quantity (ascending) - single items first
    5. KASPI_OFFER_NAME / offer_name (ascending) - alphabetical by product
    6. Date / handover (ascending) - oldest first

    This sort order groups orders by store for easier visual scanning.
    """
    colmap = map_headers(df)

    sort_cols = []
    sort_ascending = []

    # 1. Status column - cancelled/returned first (0 = top, 1 = bottom)
    if "status" in colmap:
        df = df.copy()  # Avoid SettingWithCopyWarning
        df["_status_sort"] = df[colmap["status"]].apply(
            lambda x: 0 if str(x).lower() in ['отменен', 'возвращен', 'cancelled', 'returned', 'cancelling', 'returning'] else 1
        )
        sort_cols.append("_status_sort")
        sort_ascending.append(True)

    # 2. STORE_NAME / warehouse (ascending) - group by store first
    if "warehouse" in colmap:
        sort_cols.append(colmap["warehouse"])
        sort_ascending.append(True)

    # 3. OrderID (ascending)
    if "order_id" in colmap:
        sort_cols.append(colmap["order_id"])
        sort_ascending.append(True)

    # 4. Quantity (ascending)
    if "quantity" in colmap:
        sort_cols.append(colmap["quantity"])
        sort_ascending.append(True)

    # 5. KASPI_OFFER_NAME / offer_name (ascending)
    if "offer_name" in colmap:
        sort_cols.append(colmap["offer_name"])
        sort_ascending.append(True)

    # 6. Date / handover (ascending)
    if "handover" in colmap:
        sort_cols.append(colmap["handover"])
        sort_ascending.append(True)

    if sort_cols:
        df_sorted = df.sort_values(by=sort_cols, ascending=sort_ascending, na_position='last')
        # Drop helper column
        if "_status_sort" in df_sorted.columns:
            df_sorted = df_sorted.drop(columns=["_status_sort"])
        return df_sorted.reset_index(drop=True)

    return df


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


def collect_existing_order_rows(
    crm_path: Path,
    sheet_name: str,
    table_name: str,
    order_col_abs: int
) -> Dict[str, int]:
    """
    Get dict mapping OrderID -> row number from CRM.

    Used for updating existing orders.
    """
    wb = load_workbook(filename=str(crm_path), read_only=False, data_only=True)
    try:
        ws = wb[sheet_name]
        table = _resolve_table(ws, table_name)
        start_col, start_row, end_col, end_row = _table_bounds(table)

        if not (start_col <= order_col_abs <= end_col):
            return {}

        order_rows = {}
        for row_num in range(start_row + 1, end_row + 1):
            cell = ws.cell(row=row_num, column=order_col_abs)
            val = cell.value
            if val in (None, ""):
                continue
            if isinstance(val, str) and val.startswith("="):
                continue
            # Convert float to int to match API format (741866233.0 -> "741866233")
            if isinstance(val, float):
                val = int(val)
            order_id = str(val).strip()
            if order_id:
                order_rows[order_id] = row_num
        return order_rows
    finally:
        wb.close()


def find_update_column_positions(
    crm_path: Path,
    sheet_name: str,
    start_col: int,
    end_col: int
) -> Dict[str, int]:
    """
    Find column positions for update fields within the raw Kaspi columns.

    Returns dict mapping column name -> absolute column position.
    Target columns: Статус, Дата изменения статуса, Принял, Выдал, Отменил
    """
    wb = load_workbook(filename=str(crm_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        header_row = list(ws.iter_rows(min_row=1, max_row=1, min_col=start_col, max_col=end_col))[0]

        target_columns = {
            'Статус': None,
            'Дата изменения статуса': None,
            'Принял': None,
            'Выдал': None,
            'Отменил': None,
        }

        for i, cell in enumerate(header_row):
            header = str(cell.value or '').strip()
            if header in target_columns:
                target_columns[header] = start_col + i

        return target_columns
    finally:
        wb.close()


def _require_xlwings() -> None:
    if xw is None:
        raise RuntimeError(
            "xlwings is required for Excel writes. "
            "Install with `pip install xlwings` or run with --dry-run/--no-update."
        )


def update_existing_order_columns(
    crm_path: Path,
    sheet_name: str,
    order_rows: Dict[str, int],  # order_id -> row number
    update_data: Dict[str, dict],  # order_id -> {Статус, Принял, Выдал, Отменил, ...}
    column_positions: Dict[str, int],  # column name -> absolute column position
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """
    Update specific columns for existing orders in CRM.

    Only updates: Статус, Дата изменения статуса, Принял, Выдал, Отменил
    Does NOT touch Status column (A) or formula columns.

    Uses BATCH writes by column to avoid slow cell-by-cell operations.

    Args:
        crm_path: Path to CRM file
        sheet_name: Sheet name
        order_rows: Dict mapping order_id -> Excel row number
        update_data: Dict mapping order_id -> column values to update
        column_positions: Dict mapping column name -> absolute column position
        dry_run: If True, don't write changes
        verbose: If True, print progress

    Returns:
        Number of orders updated
    """
    if not order_rows or not update_data:
        return 0

    # Find orders that exist in both
    orders_to_update = set(order_rows.keys()) & set(update_data.keys())

    if not orders_to_update:
        if verbose:
            print("  No existing orders to update")
        return 0

    if verbose:
        print(f"  Found {len(orders_to_update)} orders to update")

    if dry_run:
        print(f"  [DRY RUN] Would update {len(orders_to_update)} orders")
        return 0

    _require_xlwings()

    # Pre-build column updates: {col_pos: [(row, value), ...]}
    # This allows us to batch writes by column instead of cell-by-cell
    column_updates: Dict[int, List[Tuple[int, any]]] = {}

    for order_id in orders_to_update:
        row = order_rows[order_id]
        data = update_data[order_id]

        for col_name, col_pos in column_positions.items():
            if col_pos is None:
                continue
            if col_name in data:
                new_value = data[col_name]
                if new_value is not None:
                    if col_pos not in column_updates:
                        column_updates[col_pos] = []
                    column_updates[col_pos].append((row, new_value))

    if verbose:
        total_cells = sum(len(v) for v in column_updates.values())
        print(f"  Preparing {total_cells} cell updates across {len(column_updates)} columns...")

    # Use xlwings for writing (preserves formulas)
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(str(crm_path))
        ws = wb.sheets[sheet_name]

        # Disable calculation during updates for speed
        original_calc = app.calculation
        app.calculation = 'manual'

        # Write updates column by column
        cols_written = 0
        for col_pos, row_values in column_updates.items():
            # Sort by row for potential range optimization
            row_values.sort(key=lambda x: x[0])

            # Write all values for this column
            for row, value in row_values:
                ws.range((row, col_pos)).value = value

            cols_written += 1
            if verbose:
                print(f"    Column {cols_written}/{len(column_updates)} updated ({len(row_values)} cells)")

        # Restore calculation and save
        app.calculation = original_calc
        wb.save()
        wb.close()

        if verbose:
            print(f"  Updated {len(orders_to_update)} orders")

        return len(orders_to_update)

    finally:
        app.quit()


def build_update_data(df: pd.DataFrame, colmap: Dict[str, str]) -> Dict[str, dict]:
    """
    Build update data dict from DataFrame.

    Extracts: order_id -> {Статус, Дата изменения статуса, Принял, Выдал, Отменил}
    for updating existing orders in CRM.
    """
    update_data = {}

    # Find column names in DataFrame
    status_col = None
    status_change_col = None
    prinyal_col = None
    vydal_col = None
    otmenil_col = None

    for col in df.columns:
        col_norm = norm(col)
        if col_norm == 'статус':
            status_col = col
        elif col_norm in {'датаизменениястатуса', 'statuschangedate'}:
            status_change_col = col
        elif col_norm == 'принял':
            prinyal_col = col
        elif col_norm == 'выдал':
            vydal_col = col
        elif col_norm == 'отменил':
            otmenil_col = col

    order_col = colmap.get('order_id')
    if not order_col:
        return {}

    for _, row in df.iterrows():
        order_id = str(row.get(order_col, '')).strip()
        if not order_id:
            continue

        # Convert float order_id to int string (741866233.0 -> "741866233")
        try:
            order_id = str(int(float(order_id)))
        except (ValueError, TypeError):
            pass

        data = {}
        if status_col and pd.notna(row.get(status_col)):
            data['Статус'] = str(row[status_col])
        if status_change_col and pd.notna(row.get(status_change_col)):
            data['Дата изменения статуса'] = row[status_change_col]
        if prinyal_col:
            data['Принял'] = str(row.get(prinyal_col, '') or '')
        if vydal_col:
            data['Выдал'] = str(row.get(vydal_col, '') or '')
        if otmenil_col:
            data['Отменил'] = str(row.get(otmenil_col, '') or '')

        if data:
            update_data[order_id] = data

    return update_data


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

        if h in {"датаизменениястатуса"} and "status_change_date" in S:
            return S["status_change_date"]

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
    # Format: +7XXXXXXXXXX (Kazakhstan format)
    phone_values = []
    if "phone" in S:
        for i in range(len(df_filt)):
            v = S["phone"].iloc[i]
            if pd.isna(v):
                v = ""
            else:
                v = str(v).strip()
                # Add +7 prefix if phone has digits and doesn't already start with +
                if v and v[0] != '+':
                    # Remove any leading 8 or 7 (common Kazakhstan patterns)
                    if v.startswith('8') and len(v) == 11:
                        v = '+7' + v[1:]
                    elif v.startswith('7') and len(v) == 11:
                        v = '+7' + v[1:]
                    elif len(v) == 10:
                        v = '+7' + v
                    else:
                        v = '+7' + v  # Default: prepend +7
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
) -> Tuple[int, int]:
    """
    Append rows to CRM using xlwings (preserves formulas & external links).

    Args:
        phone_col_abs: Column for phone data (column I), or None to skip
        phone_values: List of phone strings to write

    Returns:
        Tuple of (start_row, end_row) where new rows were appended.
        Returns (0, 0) if no rows were appended.
    """
    n = len(stage_block)
    if n == 0:
        return (0, 0)

    _require_xlwings()

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

        # CRITICAL: Resize table FIRST to include new rows
        # This prevents Excel table corruption (XML errors)
        tbl_start_col = tbl.range.column
        tbl_end_col = tbl.range.columns.count + tbl_start_col - 1
        new_table_range = sh.range(
            (header_row, tbl_start_col),
            (bottom_row, tbl_end_col)
        )
        tbl.resize(new_table_range)
        print(f"  Table resized to include rows up to {bottom_row}")

        # Write date column
        date_vals = [[set_date] for _ in range(n)]
        date_range = sh.range((top_row, date_col_abs), (bottom_row, date_col_abs))
        date_range.value = date_vals
        date_range.number_format = "dd.mm.yyyy"

        # Write "Новый" marker to HEIGHT column (D = 4) for visual identification
        # Phase 12 Part 3: Helps employees see which orders were added in second import
        height_col = 4  # Column D
        height_range = sh.range((top_row, height_col), (bottom_row, height_col))
        height_range.value = [["Новый"] for _ in range(n)]
        print(f"  'Новый' marker written to column D for {n} rows")

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

        return (top_row, bottom_row)

    finally:
        app.quit()

    return (0, 0)  # If we get here somehow


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
        default=data_path("excel_ui", "ActiveOrders"),
        help="Directory containing ActiveOrders*.xlsx",
    )
    parser.add_argument(
        "--crm-file",
        type=Path,
        default=data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx"),
        help="CRM Excel file",
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
        default="today",
        help="Exact planned delivery date to filter (today, tomorrow, or YYYY-MM-DD)"
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
    parser.add_argument(
        "--update-existing",
        action="store_true",
        default=True,
        help="Update status columns for existing orders (default: True)"
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Skip updating existing orders (only append new)"
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
    print(f"  Data root: {get_data_root()}")
    print(f"  Orders dir: {args.orders_dir}")
    print(f"  CRM file: {args.crm_file}")
    print(f"  Date filter: == {end_date} (TODAY only)")
    print(f"  Append date: {append_date}")
    print()
    
    # Read and filter
    df_all, source_files = read_active_orders(args.orders_dir)
    df_filt, stats = filter_for_shipping(df_all, args.status, None, end_date)

    print(f"\nFiltered: {stats['rows_in_files']} → {stats['rows_after_filters']} rows")

    if df_filt.empty:
        print("No orders match filters. Nothing to import.")
        return

    # Sort for CRM append order (Phase 12 Part 6 - Updated)
    # Order: Status → STORE_NAME → OrderID → Quantity → KASPI_OFFER_NAME → Date
    df_filt = sort_for_crm(df_filt)
    print(f"Sorted by: Status (cancelled first), STORE_NAME, OrderID, Quantity, KASPI_OFFER_NAME, Date")

    # Inspect CRM structure
    date_abs, phone_abs, start_abs, end_abs, slice_headers = inspect_crm_sheet(
        args.crm_file, args.sheet, args.table
    )

    # Get existing order IDs for dedup
    existing_ids = collect_existing_order_ids(args.crm_file, args.sheet, args.table, start_abs)
    print(f"Existing orders in CRM: {len(existing_ids)}")

    # Update existing orders' status columns (Phase 12 Part 7)
    update_existing = args.update_existing and not args.no_update
    updated_count = 0

    if update_existing and len(existing_ids) > 0:
        print("\n3. Updating existing orders' status columns...")

        # Get order rows (order_id -> row number)
        order_rows = collect_existing_order_rows(
            args.crm_file, args.sheet, args.table, start_abs
        )

        # Find column positions for update columns
        column_positions = find_update_column_positions(
            args.crm_file, args.sheet, start_abs, end_abs
        )
        if args.verbose:
            print(f"  Update column positions: {column_positions}")

        # Build update data from source DataFrame
        colmap = map_headers(df_filt)
        update_data = build_update_data(df_filt, colmap)

        # How many orders can be updated?
        orders_to_update = set(order_rows.keys()) & set(update_data.keys())
        print(f"  Orders with status updates: {len(orders_to_update)}")

        if orders_to_update:
            updated_count = update_existing_order_columns(
                args.crm_file,
                args.sheet,
                order_rows,
                update_data,
                column_positions,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
            print(f"  Updated {updated_count} existing orders")
    else:
        if args.no_update:
            print("\n3. Skipping existing order updates (--no-update flag)")
        elif len(existing_ids) == 0:
            print("\n3. No existing orders to update")

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

    print(f"\n4. Appending new orders...")
    print(f"   Orders to append: {len(stage)}")

    if len(stage) == 0:
        if updated_count > 0:
            print(f"   No new orders to append (updated {updated_count} existing orders)")
            print(f"\n✅ Import complete! Updated {updated_count} orders, appended 0 new.")
            return
        else:
            print("   All orders already in CRM. Nothing to import or update.")
            return

    if args.dry_run:
        print("\n[DRY RUN] Would append but skipping.")
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    # Create backup before writing (Phase 12)
    backup_path = backup_crm(args.crm_file)
    print(f"  Backup created: {backup_path.name}")

    # Append via xlwings - returns (start_row, end_row) for sync
    append_start_row, append_end_row = excel_append_xlwings(
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

    # Sync NEW rows to Google Drive (Phase 12 Part 3)
    print("\n4. Syncing NEW rows to Google Drive...")
    new_rows_added = len(stage)
    try:
        # Import sync function - handle different working directories
        import sys
        project_root = Path(__file__).resolve().parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from scripts.sync_to_gdrive import sync_new_rows_to_gdrive

        # Pass actual row range to avoid date mismatch after sorting
        sync_stats = sync_new_rows_to_gdrive(
            new_rows_count=new_rows_added,  # Keep for backward compat
            start_row=append_start_row,
            end_row=append_end_row,
            dry_run=args.dry_run
        )
        print(f"   Google Drive sync: {sync_stats['rows_synced']} rows synced")
    except Exception as e:
        print(f"   WARNING: Google Drive sync failed: {e}")
        # Don't fail the import if sync fails - CRM update was successful

    print(f"\n✅ Import complete!")
    print(f"   Updated: {updated_count} existing orders")
    print(f"   Appended: {new_rows_added} new orders")
    print(f"   Archived: {archive_path}")

    # Phase 12 Part 6: Detailed statistics
    if new_rows_added > 0 and not args.dry_run:
        print("\n" + "=" * 60)
        print("  Import Statistics")
        print("=" * 60)

        # Get warehouse column for grouping
        colmap = map_headers(df_filt)
        if "warehouse" in colmap:
            store_counts = df_filt.groupby(colmap["warehouse"]).size()
            print("\n  Appended Orders by Store:")
            for store, count in sorted(store_counts.items()):
                print(f"    {store}: {count}")

        # Status summary
        if "status" in colmap:
            status_counts = df_filt.groupby(colmap["status"]).size()
            print("\n  Status Summary:")
            for status, count in sorted(status_counts.items()):
                print(f"    {status}: {count}")

        print(f"\n  Total Appended: {new_rows_added}")
        print(f"  Total in CRM (before): {len(existing_ids)}")
        print(f"  Total in CRM (after): {len(existing_ids) + new_rows_added}")
        print("=" * 60)


if __name__ == "__main__":
    main()
