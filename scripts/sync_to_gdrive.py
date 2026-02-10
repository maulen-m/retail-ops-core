#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 12 Part 3: Sync CRM rows to Google Drive Excel file.

Targets: Kaspi_drive_sales_v1.xlsx -> sheet 'sales_kaspi_drive' -> table 'drive'

Modes:
1) NEW rows sync (incremental append from last import)
2) Pending-today sync (copy/paste pending orders for target date with formatting)

Environment:
- AB_GDRIVE_KASPI_SALES_PATH (or GDRIVE_KASPI_SALES_PATH) overrides Drive path

Usage:
    python scripts/sync_to_gdrive.py --new-rows 5
    python scripts/sync_to_gdrive.py --new-rows 10 --dry-run
    python scripts/sync_to_gdrive.py --pending-date today --validate
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Iterable

from dateutil import parser as dtp
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import xlwings as xw

from core.paths import data_path

# Source sheet (in CRM)
CRM_SHEET_NAME = "SALES_KSP_CRM_1"
CRM_TABLE_NAME = "tb_SalesRaw"

# Target sheet and table (in Google Drive file)
GDRIVE_SHEET_NAME = "sales_kaspi_drive"
GDRIVE_TABLE_NAME = "drive"

# Columns to sync: A to AZ (52 columns)
SYNC_COLS_END = "AZ"

READY_STATUS = "Ожидает передачи курьеру"
ALMATY_TZ = ZoneInfo("Asia/Almaty")
GDRIVE_BACKUP_ROOT = Path.home() / "Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business"
GDRIVE_BACKUP_SUBDIR = "Kaspi_drive_sales_backups"
GDRIVE_BACKUP_PREFIX = "Kaspi_drive_sales_v1"


def backup_gdrive_file(gdrive_path: Path) -> Optional[Path]:
    """Create a timestamped backup of the Google Drive sales file before edits."""
    if not gdrive_path.exists():
        raise FileNotFoundError(f"Google Drive file not found: {gdrive_path}")

    backup_root = GDRIVE_BACKUP_ROOT / GDRIVE_BACKUP_SUBDIR
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(ALMATY_TZ).strftime("%Y-%m-%d_%H%M%S")
    backup_path = backup_root / f"{GDRIVE_BACKUP_PREFIX}_{ts}.xlsx"
    shutil.copy2(gdrive_path, backup_path)
    return backup_path


def resolve_crm_path(path: Optional[Path]) -> Path:
    if path:
        return path
    env_path = os.environ.get("AB_CRM_PATH") or os.environ.get("CRM_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")


def resolve_gdrive_path(path: Optional[Path]) -> Path:
    if path:
        return path
    env_path = os.environ.get("AB_GDRIVE_KASPI_SALES_PATH") or os.environ.get("GDRIVE_KASPI_SALES_PATH")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / "Library/CloudStorage/GoogleDrive-maintainer@example.com/My Drive/Business/Shared/Kaspi/Kaspi orders/Kaspi_drive_sales_v1.xlsx"


def clean_order_id(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.strip()


def parse_excel_date(value: object) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        base = datetime(1899, 12, 30)
        return (base + timedelta(days=float(value))).date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            try:
                return datetime.strptime(text, "%Y-%m-%d").date()
            except ValueError:
                pass
        try:
            return dtp.parse(text, dayfirst=True).date()
        except Exception:
            return None
    return None


def resolve_target_date(value: object) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip().lower()
    if text in ("", "today"):
        return datetime.now(ALMATY_TZ).date()
    if text == "tomorrow":
        return datetime.now(ALMATY_TZ).date() + timedelta(days=1)
    parsed = parse_excel_date(text)
    if parsed:
        return parsed
    raise ValueError(f"Could not parse target date: {value}")


def find_header_index(headers: Iterable[object], candidates: Iterable[str]) -> Optional[int]:
    normalized = [str(h or "").strip() for h in headers]
    for name in candidates:
        if name in normalized:
            return normalized.index(name)
    return None


def apply_formats(src_range, dst_range) -> bool:
    """Best-effort format copy across macOS/Windows Excel automation."""
    for copy_method in ("Copy", "copy"):
        try:
            getattr(src_range.api, copy_method)()
        except Exception:
            continue
        for paste_method in ("PasteSpecial", "paste_special"):
            for kwargs in ({"Paste": -4122}, {"paste": -4122}):
                try:
                    getattr(dst_range.api, paste_method)(**kwargs)
                    try:
                        dst_range.api.Application.CutCopyMode = False
                    except Exception:
                        pass
                    return True
                except Exception:
                    continue
    return False


def sync_new_rows_to_gdrive(
    crm_path: Optional[Path] = None,
    gdrive_path: Optional[Path] = None,
    new_rows_count: int = 0,
    start_row: int = None,
    end_row: int = None,
    dry_run: bool = False,
) -> dict:
    """
    Sync only NEW rows from CRM to Google Drive file.

    Appends specified rows from CRM to the 'drive' table on 'sales_kaspi_drive' sheet.

    Args:
        crm_path: Source CRM file path
        gdrive_path: Target Google Drive file path
        new_rows_count: DEPRECATED - Number of new rows (use start_row/end_row instead)
        start_row: Actual start row in CRM (1-indexed, from import script)
        end_row: Actual end row in CRM (1-indexed)
        dry_run: If True, only show what would be synced

    Returns:
        dict with stats: rows_synced, dry_run

    Note:
        If start_row/end_row are provided, they are used directly.
        Otherwise falls back to new_rows_count (for backward compatibility).
    """
    crm_path = resolve_crm_path(crm_path)
    gdrive_path = resolve_gdrive_path(gdrive_path)

    print(f"Source: {crm_path}")
    print(f"Target: {gdrive_path}")
    print(f"Target sheet: '{GDRIVE_SHEET_NAME}', table: '{GDRIVE_TABLE_NAME}'")

    # Check if we have rows to sync
    has_explicit_range = start_row is not None and end_row is not None
    if not has_explicit_range and new_rows_count <= 0:
        print("  No new rows to sync (new_rows_count=0)")
        return {"rows_synced": 0, "dry_run": dry_run}

    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    if not gdrive_path.exists():
        raise FileNotFoundError(
            f"Google Drive file not found: {gdrive_path}. "
            "The file must exist with the 'drive' table already set up."
        )

    if not dry_run:
        backup_path = backup_gdrive_file(gdrive_path)
        print(f"  Backup saved: {backup_path}")

    app = None
    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False

        # Open source CRM (read-only)
        wb_src = app.books.open(str(crm_path), read_only=True, update_links=False)
        sh_src = wb_src.sheets[CRM_SHEET_NAME]

        # Determine row range to sync
        if has_explicit_range:
            # Use explicit start_row/end_row (preferred - avoids date mismatch)
            first_new_row = start_row
            last_row_crm = end_row
            actual_count = end_row - start_row + 1
            print(f"  Using explicit row range: {first_new_row}-{last_row_crm}")
        else:
            # Legacy: calculate from new_rows_count (may sync wrong dates if sorted)
            last_row_crm = sh_src.range("A1").end("down").row
            first_new_row = last_row_crm - new_rows_count + 1
            if first_new_row < 2:  # Can't go above row 2 (row 1 is header)
                first_new_row = 2
                new_rows_count = last_row_crm - 1
            actual_count = new_rows_count
            print(f"  Using legacy row calculation: last {actual_count} rows")

        # Get values for new rows only (columns A to AZ)
        new_data_range = sh_src.range(f"A{first_new_row}:{SYNC_COLS_END}{last_row_crm}")
        new_values = new_data_range.value

        # Handle single row case (xlwings returns list instead of list of lists)
        if actual_count == 1 and not isinstance(new_values[0], list):
            new_values = [new_values]

        print(f"  Found {len(new_values)} new rows to sync (rows {first_new_row}-{last_row_crm})")

        if dry_run:
            print("  [DRY-RUN] Would sync to Google Drive")
            wb_src.close()
            return {"rows_synced": len(new_values), "dry_run": True}

        # Open target Google Drive file
        wb_dst = app.books.open(str(gdrive_path), update_links=False)

        # Get target sheet
        try:
            sh_dst = wb_dst.sheets[GDRIVE_SHEET_NAME]
        except Exception:
            raise RuntimeError(
                f"Sheet '{GDRIVE_SHEET_NAME}' not found in {gdrive_path.name}. "
                "Please create the sheet and 'drive' table first."
            )

        # Get the 'drive' table
        try:
            tbl = sh_dst.tables[GDRIVE_TABLE_NAME]
        except KeyError:
            # Try to find any table
            tables = list(sh_dst.tables)
            if not tables:
                raise RuntimeError(
                    f"Table '{GDRIVE_TABLE_NAME}' not found on sheet '{GDRIVE_SHEET_NAME}'. "
                    "Please create the table first."
                )
            tbl = tables[0]
            print(f"  WARNING: Using table '{tbl.name}' instead of '{GDRIVE_TABLE_NAME}'")

        # Calculate where new rows go in destination
        total_rows_before = tbl.range.rows.count
        header_row = tbl.range.row
        top_row = header_row + total_rows_before  # First row after current data
        bottom_row = top_row + len(new_values) - 1
        n = len(new_values)

        print(f"  Appending {n} rows to '{tbl.name}' starting at row {top_row}")

        # CRITICAL: Resize table FIRST to include new rows (prevents XML corruption)
        tbl_start_col = tbl.range.column
        tbl_end_col = tbl.range.columns.count + tbl_start_col - 1
        new_table_range = sh_dst.range(
            (header_row, tbl_start_col),
            (bottom_row, tbl_end_col)
        )
        tbl.resize(new_table_range)
        print(f"  Table resized to include rows up to {bottom_row}")

        # Write new values using BULK column writes (fast)
        # This is ~40x faster than cell-by-cell writes for Google Drive files
        data_cols = len(new_values[0]) if new_values else 0
        n_rows = len(new_values)

        print(f"  Writing {n_rows} rows ({data_cols} columns)...")

        # Write by column instead of cell-by-cell (reduces COM calls from ~2000 to ~50)
        # IMPORTANT: Use tbl_start_col to respect table's starting column position
        for col_idx in range(data_cols):
            # Extract column values as [[val1], [val2], ...]
            col_values = [[row[col_idx] if col_idx < len(row) else None] for row in new_values]

            # Skip entirely empty columns for performance
            if all(v[0] is None or v[0] == "" for v in col_values):
                continue

            # Bulk write entire column at once, respecting table's starting column
            target_col = tbl_start_col + col_idx
            col_range = sh_dst.range((top_row, target_col), (bottom_row, target_col))
            col_range.value = col_values

            # Progress indicator every 10 columns
            if (col_idx + 1) % 10 == 0:
                print(f"    Columns written: {col_idx + 1}/{data_cols}")

        print(f"  ✓ All columns written")

        # Copy formatting from existing data row to new rows
        # Use the row just before new data as the template
        template_row = top_row - 1
        if template_row > header_row:  # Make sure we have at least one data row
            print(f"  Copying cell formatting from row {template_row}...")

            # Get format source range (one row, all columns in table)
            format_source = sh_dst.range(
                (template_row, tbl_start_col),
                (template_row, tbl_end_col)
            )

            # Apply format to all new rows
            format_target = sh_dst.range(
                (top_row, tbl_start_col),
                (bottom_row, tbl_end_col)
            )

            # Copy format using Excel's API (includes colors, fonts, borders)
            if apply_formats(format_source, format_target):
                print(f"  ✓ Formatting applied to {n_rows} new rows")
            else:
                print("  WARNING: Could not apply formatting (values synced)")

        print(f"  Saving to Google Drive...")
        wb_dst.save()
        wb_dst.close()
        wb_src.close()

        print(f"  ✅ Synced {n} rows to Google Drive")
        return {"rows_synced": n, "dry_run": False}

    finally:
        if app:
            app.quit()


def sync_pending_orders_to_gdrive(
    crm_path: Optional[Path] = None,
    gdrive_path: Optional[Path] = None,
    target_date: object = "today",
    status_value: str = READY_STATUS,
    sheet_name: str = CRM_SHEET_NAME,
    table_name: str = CRM_TABLE_NAME,
    dry_run: bool = False,
    validate: bool = True,
) -> dict:
    """
    Copy/paste pending orders for target date from CRM to Google Drive file.

    Preserves CRM formatting by copying from CRM rows and pasting values+formats.
    Dedupes by order_id + planned_date for idempotency.
    """
    crm_path = resolve_crm_path(crm_path)
    gdrive_path = resolve_gdrive_path(gdrive_path)
    target_date = resolve_target_date(target_date)

    print(f"Source: {crm_path}")
    print(f"Target: {gdrive_path}")
    print(f"Target sheet: '{GDRIVE_SHEET_NAME}', table: '{GDRIVE_TABLE_NAME}'")
    print(f"Pending date: {target_date.isoformat()} | Status: {status_value}")

    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    if not gdrive_path.exists():
        raise FileNotFoundError(
            f"Google Drive file not found: {gdrive_path}. "
            "The file must exist with the 'drive' table already set up."
        )

    if not dry_run:
        backup_path = backup_gdrive_file(gdrive_path)
        print(f"  Backup saved: {backup_path}")

    app = None
    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False

        wb_src = app.books.open(str(crm_path), read_only=True, update_links=False)
        sh_src = wb_src.sheets[sheet_name]

        try:
            tbl_src = sh_src.tables[table_name]
        except KeyError as exc:
            wb_src.close()
            raise RuntimeError(f"Table '{table_name}' not found in CRM sheet '{sheet_name}'.") from exc

        if tbl_src.data_body_range is None:
            wb_src.close()
            print("  No CRM data rows to sync.")
            return {"rows_synced": 0, "dry_run": dry_run}

        headers = [str(h or "").strip() for h in tbl_src.header_row_range.value]
        order_idx = find_header_index(headers, ("OrderID", "№ заказа"))
        status_idx = find_header_index(headers, ("Статус", "Status"))
        planned_idx = find_header_index(headers, ("Плановая дата передачи курьеру", "PLANNED_SHIPPING_DATE"))
        crm_header_map = {header: idx for idx, header in enumerate(headers) if header}

        if order_idx is None or status_idx is None or planned_idx is None:
            wb_src.close()
            raise RuntimeError("Required CRM headers missing (OrderID/Статус/Плановая дата передачи курьеру).")

        data_range = tbl_src.data_body_range
        data_values = data_range.value or []
        if data_values and not isinstance(data_values[0], list):
            data_values = [data_values]

        src_start_row = data_range.row
        src_start_col = data_range.column
        src_end_col = src_start_col + data_range.columns.count - 1

        pending_rows: list[tuple[int, str, date, list]] = []
        for offset, row in enumerate(data_values):
            status = str(row[status_idx] or "").strip()
            if status != status_value:
                continue
            planned = parse_excel_date(row[planned_idx])
            if planned != target_date:
                continue
            order_id = clean_order_id(row[order_idx])
            if not order_id:
                continue
            row_num = src_start_row + offset
            pending_rows.append((row_num, order_id, planned, row))

        if not pending_rows:
            wb_src.close()
            print("  No pending rows matched criteria.")
            return {"rows_synced": 0, "dry_run": dry_run}

        wb_dst = app.books.open(str(gdrive_path), update_links=False)
        try:
            sh_dst = wb_dst.sheets[GDRIVE_SHEET_NAME]
        except Exception as exc:
            wb_src.close()
            wb_dst.close()
            raise RuntimeError(
                f"Sheet '{GDRIVE_SHEET_NAME}' not found in {gdrive_path.name}. "
                "Please create the sheet and 'drive' table first."
            ) from exc

        try:
            tbl_dst = sh_dst.tables[GDRIVE_TABLE_NAME]
        except KeyError:
            tables = list(sh_dst.tables)
            if not tables:
                wb_src.close()
                wb_dst.close()
                raise RuntimeError(
                    f"Table '{GDRIVE_TABLE_NAME}' not found on sheet '{GDRIVE_SHEET_NAME}'. "
                    "Please create the table first."
                )
            tbl_dst = tables[0]
            print(f"  WARNING: Using table '{tbl_dst.name}' instead of '{GDRIVE_TABLE_NAME}'")

        dst_headers = [str(h or "").strip() for h in tbl_dst.header_row_range.value]
        dst_order_idx = find_header_index(dst_headers, ("OrderID", "№ заказа"))
        dst_planned_idx = find_header_index(dst_headers, ("Плановая дата передачи курьеру", "PLANNED_SHIPPING_DATE"))
        dst_header_map = {header: idx for idx, header in enumerate(dst_headers) if header}
        headers_match = headers == dst_headers
        dst_to_crm_idx = [
            crm_header_map.get(header) if header in crm_header_map else None
            for header in dst_headers
        ]

        def build_mapped_values(row_values: list, base_values: Optional[list] = None) -> list:
            if headers_match:
                return row_values
            mapped = list(base_values) if base_values is not None else [None] * len(dst_headers)
            for dst_idx, crm_idx in enumerate(dst_to_crm_idx):
                if crm_idx is None:
                    continue
                if crm_idx < len(row_values):
                    mapped[dst_idx] = row_values[crm_idx]
            return mapped
        if dst_order_idx is None or dst_planned_idx is None:
            wb_src.close()
            wb_dst.close()
            raise RuntimeError("Required Drive headers missing (OrderID/Плановая дата передачи курьеру).")

        # Map existing rows by key for idempotent updates
        existing_rows: dict[str, int] = {}
        if tbl_dst.data_body_range is not None:
            dst_data = tbl_dst.data_body_range
            dst_values = dst_data.value or []
            if dst_values and not isinstance(dst_values[0], list):
                dst_values = [dst_values]
            dst_start_row = dst_data.row
            for offset, row in enumerate(dst_values):
                oid = clean_order_id(row[dst_order_idx])
                pdate = parse_excel_date(row[dst_planned_idx])
                if oid and pdate:
                    key = f"{oid}|{pdate.isoformat()}"
                    existing_rows[key] = dst_start_row + offset

        # Filter pending rows against existing keys
        pending_updates = []
        pending_appends = []
        for row_num, oid, pdate, row_values in pending_rows:
            key = f"{oid}|{pdate.isoformat()}"
            if key in existing_rows:
                pending_updates.append((existing_rows[key], row_num, oid, pdate, row_values))
            else:
                pending_appends.append((row_num, oid, pdate, row_values))

        if not pending_updates and not pending_appends:
            wb_src.close()
            wb_dst.close()
            print("  All pending rows already synced.")
            return {"rows_synced": 0, "dry_run": dry_run}

        if dry_run:
            wb_src.close()
            wb_dst.close()
            total_rows = len(pending_updates) + len(pending_appends)
            print(f"  [DRY-RUN] Would sync {total_rows} pending rows")
            return {"rows_synced": total_rows, "dry_run": True}

        tbl_start_col = tbl_dst.range.column
        tbl_end_col = tbl_start_col + tbl_dst.range.columns.count - 1
        src_cols = len(headers)
        dst_cols = len(dst_headers)
        if headers_match and src_cols != dst_cols:
            wb_src.close()
            wb_dst.close()
            raise RuntimeError(
                f"Column mismatch: CRM table has {src_cols} cols, Drive table has {dst_cols} cols."
            )

        # Update existing rows first
        format_failed = False
        for dest_row_num, src_row_num, _, _, row_values in pending_updates:
            src_row = sh_src.range((src_row_num, src_start_col), (src_row_num, src_end_col))
            dst_row = sh_dst.range((dest_row_num, tbl_start_col), (dest_row_num, tbl_end_col))

            base_values = dst_row.value
            if base_values and not isinstance(base_values, list):
                base_values = [base_values]
            mapped_values = build_mapped_values(row_values, base_values)
            try:
                src_row.copy(dst_row)
                dst_row.value = mapped_values
            except Exception:
                dst_row.value = mapped_values
                if not apply_formats(src_row, dst_row):
                    format_failed = True

        # Append new rows if needed
        top_row = None
        bottom_row = None
        if pending_appends:
            total_rows_before = tbl_dst.range.rows.count
            header_row = tbl_dst.range.row
            top_row = header_row + total_rows_before
            bottom_row = top_row + len(pending_appends) - 1

            # Resize table to include new rows
            new_table_range = sh_dst.range(
                (header_row, tbl_start_col),
                (bottom_row, tbl_end_col)
            )
            tbl_dst.resize(new_table_range)

            for idx, (row_num, _, _, row_values) in enumerate(pending_appends):
                dest_row_num = top_row + idx
                src_row = sh_src.range((row_num, src_start_col), (row_num, src_end_col))
                dst_row = sh_dst.range((dest_row_num, tbl_start_col), (dest_row_num, tbl_end_col))
                mapped_values = build_mapped_values(row_values)
                try:
                    src_row.copy(dst_row)
                    dst_row.value = mapped_values
                except Exception:
                    dst_row.value = mapped_values
                    if not apply_formats(src_row, dst_row):
                        format_failed = True

        if format_failed:
            print("  WARNING: Some row formats could not be applied (values synced).")

        if validate:
            expected_keys = {
                f"{oid}|{pdate.isoformat()}" for _, _, oid, pdate, _ in pending_updates
            } | {
                f"{oid}|{pdate.isoformat()}" for _, oid, pdate, _ in pending_appends
            }
            actual_keys = set()
            if tbl_dst.data_body_range is not None:
                all_values = tbl_dst.data_body_range.value or []
                if all_values and not isinstance(all_values[0], list):
                    all_values = [all_values]
                for row in all_values:
                    oid = clean_order_id(row[dst_order_idx])
                    pdate = parse_excel_date(row[dst_planned_idx])
                    if oid:
                        actual_keys.add(f"{oid}|{pdate.isoformat() if pdate else ''}")

            if not expected_keys.issubset(actual_keys):
                missing = sorted(expected_keys - actual_keys)
                wb_src.close()
                wb_dst.close()
                raise RuntimeError(f"Drive validation failed, missing rows: {missing[:5]}")

            print(f"  ✅ Validation OK ({len(expected_keys)} rows)")

        wb_dst.save()
        wb_dst.close()
        wb_src.close()

        total_rows = len(pending_updates) + len(pending_appends)
        print(f"  ✅ Synced {total_rows} pending rows to Google Drive")
        return {"rows_synced": total_rows, "dry_run": False}

    finally:
        if app:
            app.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Sync CRM rows to Google Drive (new rows or pending orders)"
    )
    parser.add_argument(
        "--new-rows",
        type=int,
        default=0,
        help="Number of new rows to sync from CRM (from last import)"
    )
    parser.add_argument(
        "--pending-date",
        default=None,
        help="If set, sync pending orders for this date (today, tomorrow, or YYYY-MM-DD)"
    )
    parser.add_argument(
        "--pending-status",
        default=READY_STATUS,
        help="Status value to treat as pending (default: READY)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate appended pending rows after sync"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually syncing"
    )
    parser.add_argument(
        "--crm",
        type=Path,
        default=None,
        help="Source CRM file path"
    )
    parser.add_argument(
        "--gdrive",
        type=Path,
        default=None,
        help="Target Google Drive file path"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Google Drive Sync (Phase 12 Part 3)")
    print("=" * 60)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        if args.pending_date:
            stats = sync_pending_orders_to_gdrive(
                crm_path=args.crm,
                gdrive_path=args.gdrive,
                target_date=args.pending_date,
                status_value=args.pending_status,
                dry_run=args.dry_run,
                validate=args.validate,
            )
        else:
            stats = sync_new_rows_to_gdrive(
                args.crm, args.gdrive, args.new_rows, None, None, args.dry_run
            )
        print(f"\nSync complete: {stats['rows_synced']} rows")
        if stats["dry_run"]:
            print("  (dry-run mode - no changes made)")
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        print("  Make sure Google Drive is mounted and synced.")
        raise SystemExit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        # Try to send error alert
        try:
            from core.alerts.error_alerts import send_error_alert
            send_error_alert(str(e), "sync_to_gdrive")
        except Exception:
            pass  # Don't fail if alert fails
        raise


if __name__ == "__main__":
    main()
