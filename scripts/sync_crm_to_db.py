#!/usr/bin/env python3
"""
Daily CRM -> Database sync script.

Scheduled to run at 13:00 GMT+5 (08:00 UTC) daily.
Syncs sales from SALES_KSP_CRM_V3.xlsx to sales_fact_v2 table.

Usage:
    python scripts/sync_crm_to_db.py
    python scripts/sync_crm_to_db.py --dry-run
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.ingest.sales_ingest import ingest_sales


DEFAULT_CRM_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET = "SALES_KSP_CRM_1"


def main():
    parser = argparse.ArgumentParser(description="Sync CRM to database")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--file", type=Path, default=DEFAULT_CRM_PATH,
                        help="CRM file path")
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET,
                        help="Sheet name")
    parser.add_argument("--no-ledger", action="store_true",
                        help="Skip ledger events (faster)")
    args = parser.parse_args()

    print(f"=" * 60)
    print(f"CRM -> DB Sync: {datetime.now().isoformat()}")
    print(f"=" * 60)
    print(f"Source: {args.file}")
    print(f"Sheet:  {args.sheet}")

    if not args.file.exists():
        print(f"ERROR: CRM file not found: {args.file}")
        sys.exit(1)

    if args.dry_run:
        print("\n[DRY RUN] Parsing only, not writing to DB")
        # Import parse function for dry run
        from core.ingest.sales_ingest import parse_sales_excel
        try:
            records = parse_sales_excel(str(args.file), args.sheet)
            print(f"Parsed {len(records)} records")
            # Count mapped vs unmapped
            mapped = sum(1 for r in records if r["sku_id"])
            unmapped = len(records) - mapped
            print(f"  Mapped:   {mapped}")
            print(f"  Unmapped: {unmapped}")
        except Exception as e:
            print(f"ERROR parsing: {e}")
            sys.exit(1)
        return

    # Run actual ingest
    try:
        result = ingest_sales(
            xlsx_path=str(args.file),
            sheet_name=args.sheet,
            apply_to_ledger=not args.no_ledger,
            source_file=args.file.name,
        )
    except Exception as e:
        print(f"ERROR during ingest: {e}")
        sys.exit(1)

    print(f"\nSync Results:")
    print(f"  Inserted: {result.get('inserted', 0)}")
    print(f"  Skipped (dupes): {result.get('skipped', 0)}")
    print(f"  Returns processed: {result.get('returns_processed', 0)}")
    print(f"  Ledger events: {result.get('ledger_events', 0)}")

    if result.get('unmapped'):
        print(f"\n  Unmapped offers: {len(result['unmapped'])}")
        for item in result['unmapped'][:5]:
            print(f"    - {item}")

    if result.get('errors'):
        print(f"\n  Errors: {len(result['errors'])}")
        for err in result['errors'][:5]:
            print(f"    - {err}")

    print(f"\n{'=' * 60}")
    print(f"Sync complete!")


if __name__ == "__main__":
    main()
