#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 12 Part 3: Sync NEW CRM rows to Google Drive Excel file.

Appends only the NEWLY added rows from CRM to the Google Drive file.
Target: Kaspi_drive_sales_v1.xlsx -> sheet 'sales_kaspi_drive' -> table 'drive'

This creates an incremental sync that:
- Only adds the new rows from the latest import
- Appends to the existing 'drive' table
- Writes values only (no formulas)
- Properly resizes the table to prevent corruption

Usage:
    python scripts/sync_to_gdrive.py --new-rows 5
    python scripts/sync_to_gdrive.py --new-rows 10 --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Any

import xlwings as xw


# Default paths
CRM_PATH = Path("~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx")
GDRIVE_PATH = Path(
    "~/Library/CloudStorage/GoogleDrive-maintainer@example.com/"
    "My Drive/Business/Shared/Kaspi/Kaspi orders/Kaspi_drive_sales_v1.xlsx"
)

# Source sheet (in CRM)
CRM_SHEET_NAME = "SALES_KSP_CRM_1"

# Target sheet and table (in Google Drive file)
GDRIVE_SHEET_NAME = "sales_kaspi_drive"
GDRIVE_TABLE_NAME = "drive"

# Columns to sync: A to AZ (52 columns)
SYNC_COLS_END = "AZ"


def sync_new_rows_to_gdrive(
    crm_path: Path = CRM_PATH,
    gdrive_path: Path = GDRIVE_PATH,
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

    app = None
    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False

        # Open source CRM (read-only)
        wb_src = app.books.open(str(crm_path), read_only=True)
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
        wb_dst = app.books.open(str(gdrive_path))

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

        print(f"  Saving to Google Drive...")
        wb_dst.save()
        wb_dst.close()
        wb_src.close()

        print(f"  ✅ Synced {n} rows to Google Drive")
        return {"rows_synced": n, "dry_run": False}

    finally:
        if app:
            app.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Sync NEW CRM rows to Google Drive (values only, append to 'drive' table)"
    )
    parser.add_argument(
        "--new-rows",
        type=int,
        default=0,
        help="Number of new rows to sync from CRM (from last import)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually syncing"
    )
    parser.add_argument(
        "--crm",
        type=Path,
        default=CRM_PATH,
        help="Source CRM file path"
    )
    parser.add_argument(
        "--gdrive",
        type=Path,
        default=GDRIVE_PATH,
        help="Target Google Drive file path"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Google Drive Sync (Phase 12 Part 3)")
    print("=" * 60)
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        stats = sync_new_rows_to_gdrive(
            args.crm, args.gdrive, args.new_rows, args.dry_run
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
