#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 12 Part 3: Sync CRM data to Google Drive Excel file.

Copies all order rows (A-AZ) from SALES_KSP_CRM_V3.xlsx to
Kaspi_drive_sales_v1.xlsx as values (no formulas).

This creates a "mirror" of the CRM on Google Drive that:
- Contains all data as values (no formulas)
- Is accessible to other team members
- Preserves basic formatting

Usage:
    python scripts/sync_to_gdrive.py
    python scripts/sync_to_gdrive.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime

import xlwings as xw


# Default paths
CRM_PATH = Path("~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx")
GDRIVE_PATH = Path(
    "~/Library/CloudStorage/GoogleDrive-maintainer@example.com/"
    "My Drive/Business/Shared/Kaspi/Kaspi orders/Kaspi_drive_sales_v1.xlsx"
)
SHEET_NAME = "SALES_KSP_CRM_1"


def sync_crm_to_gdrive(
    crm_path: Path = CRM_PATH,
    gdrive_path: Path = GDRIVE_PATH,
    dry_run: bool = False,
) -> dict:
    """
    Sync CRM data to Google Drive file.

    Full sync: replaces entire content of Google Drive file with CRM data.
    All formulas are converted to values.

    Args:
        crm_path: Source CRM file path
        gdrive_path: Target Google Drive file path
        dry_run: If True, only show what would be synced

    Returns:
        dict with stats: rows_synced, columns, dry_run
    """
    print(f"Source: {crm_path}")
    print(f"Target: {gdrive_path}")

    if not crm_path.exists():
        raise FileNotFoundError(f"CRM file not found: {crm_path}")

    if not gdrive_path.parent.exists():
        raise FileNotFoundError(
            f"Google Drive folder not mounted or accessible: {gdrive_path.parent}"
        )

    app = None
    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False

        # Open source CRM (read-only to prevent accidental changes)
        wb_src = app.books.open(str(crm_path), read_only=True)
        sh_src = wb_src.sheets[SHEET_NAME]

        # Find data range: from A1 to AZ + last row with data
        # Use column A to find last row (most reliable)
        last_row = sh_src.range("A1").end("down").row

        # Safety check: don't sync if less than 2 rows (header only)
        if last_row < 2:
            print("  WARNING: CRM appears empty (no data rows)")
            wb_src.close()
            return {"rows_synced": 0, "columns": "A-AZ", "dry_run": dry_run}

        # Get all data as values (formulas evaluated)
        data_range = sh_src.range(f"A1:AZ{last_row}")
        values = data_range.value

        print(f"  Found {last_row} rows (1 header + {last_row - 1} data), columns A-AZ")

        if dry_run:
            print("  [DRY-RUN] Would sync to Google Drive")
            wb_src.close()
            return {"rows_synced": last_row, "columns": "A-AZ", "dry_run": True}

        # Open or create target file
        if gdrive_path.exists():
            wb_dst = app.books.open(str(gdrive_path))
        else:
            wb_dst = app.books.add()

        # Get or create sheet
        sheet_names = [s.name for s in wb_dst.sheets]
        if SHEET_NAME in sheet_names:
            sh_dst = wb_dst.sheets[SHEET_NAME]
            sh_dst.clear()  # Clear existing data
        else:
            sh_dst = wb_dst.sheets.add(SHEET_NAME)

        # Write values (this converts all formulas to their computed values)
        sh_dst.range("A1").value = values

        # Save to Google Drive path
        wb_dst.save(str(gdrive_path))
        wb_dst.close()
        wb_src.close()

        print(f"  Synced {last_row} rows to Google Drive")
        return {"rows_synced": last_row, "columns": "A-AZ", "dry_run": False}

    finally:
        if app:
            app.quit()


def main():
    parser = argparse.ArgumentParser(
        description="Sync CRM data to Google Drive (values only, no formulas)"
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
        stats = sync_crm_to_gdrive(args.crm, args.gdrive, args.dry_run)
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
