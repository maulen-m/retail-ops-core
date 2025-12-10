#!/usr/bin/env python3
"""
TASK-177: Sales Ingestion CLI (Phase 10)

Ingests sales data from Excel file to sales_fact_v2 and stock_ledger.

Usage:
    python scripts/ingest_sales_v2.py                     # Use default file
    python scripts/ingest_sales_v2.py --file path/to/file.xlsx
    python scripts/ingest_sales_v2.py --dry-run           # Parse only, no DB changes
    python scripts/ingest_sales_v2.py --show-unmapped     # Show unmapped offers
    python scripts/ingest_sales_v2.py --no-ledger         # Skip ledger events
    python scripts/ingest_sales_v2.py --sheet "Sheet1"    # Specify sheet name
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ingest.sales_ingest import (
    parse_sales_excel,
    ingest_sales,
    get_unmapped_offers,
)


DEFAULT_SALES_FILE = "excel_ui/SALES_KSP_CRM_V3.xlsx"
DEFAULT_SHEET = "SALES_KSP_CRM_1"


def main():
    parser = argparse.ArgumentParser(
        description="Ingest sales data from Excel to database"
    )
    parser.add_argument(
        "--file", "-f",
        default=DEFAULT_SALES_FILE,
        help=f"Path to Excel file (default: {DEFAULT_SALES_FILE})",
    )
    parser.add_argument(
        "--sheet", "-s",
        default=DEFAULT_SHEET,
        help=f"Sheet name (default: {DEFAULT_SHEET})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse file only, don't write to database",
    )
    parser.add_argument(
        "--show-unmapped",
        action="store_true",
        help="Show unmapped kaspi_offer_name entries",
    )
    parser.add_argument(
        "--no-ledger",
        action="store_true",
        help="Skip creating ledger events (sales_fact_v2 only)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed output",
    )

    args = parser.parse_args()

    # Check if file exists
    xlsx_path = Path(args.file)
    if not xlsx_path.exists():
        print(f"ERROR: File not found: {xlsx_path}")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"Sales Ingestion v2")
    print(f"{'=' * 60}")
    print(f"File:    {xlsx_path}")
    print(f"Sheet:   {args.sheet}")
    print(f"Options: dry_run={args.dry_run}, no_ledger={args.no_ledger}")

    # Show unmapped offers
    if args.show_unmapped:
        print(f"\n--- Unmapped Offers ---")
        unmapped = get_unmapped_offers(str(xlsx_path), args.sheet)
        if unmapped:
            print(f"Found {len(unmapped)} unmapped kaspi_offer_name entries:\n")
            for item in unmapped[:20]:
                print(f"  [{item['order_count']:3} orders] {item['kaspi_offer_name']}")
            if len(unmapped) > 20:
                print(f"  ... and {len(unmapped) - 20} more")
        else:
            print("No unmapped offers found.")
        print("")

    # Parse file
    print(f"\n--- Parsing File ---")
    try:
        records = parse_sales_excel(str(xlsx_path), args.sheet)
        print(f"Parsed {len(records)} sale records")
    except Exception as e:
        print(f"ERROR parsing file: {e}")
        sys.exit(1)

    if args.verbose:
        # Show sample records
        print(f"\nSample records:")
        for rec in records[:3]:
            print(f"  {rec['order_id']}: {rec['kaspi_offer_name'][:50]}...")

    if args.dry_run:
        print(f"\n--- Dry Run Mode ---")
        print(f"Would process {len(records)} records")

        # Count mapped vs unmapped
        mapped = sum(1 for r in records if r["sku_id"])
        unmapped = len(records) - mapped
        print(f"  Mapped:   {mapped}")
        print(f"  Unmapped: {unmapped}")

        # Count by store
        stores = {}
        for r in records:
            store = r.get("store_code", "UNKNOWN")
            stores[store] = stores.get(store, 0) + 1
        print(f"\nBy store:")
        for store, count in sorted(stores.items()):
            print(f"  {store}: {count}")

        print(f"\nNo database changes made (dry run).")
        return

    # Ingest to database
    print(f"\n--- Ingesting to Database ---")
    result = ingest_sales(
        xlsx_path=str(xlsx_path),
        sheet_name=args.sheet,
        apply_to_ledger=not args.no_ledger,
        source_file=xlsx_path.name,
    )

    # Print results
    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"Inserted:          {result['inserted']}")
    print(f"Skipped (dedup):   {result['skipped']}")
    print(f"Returns processed: {result['returns_processed']}")
    print(f"Ledger events:     {result['ledger_events']}")

    if result["unmapped"]:
        print(f"\nUnmapped offers: {len(result['unmapped'])}")
        if args.verbose:
            for item in result["unmapped"][:5]:
                print(f"  - Order {item['order_id']}: {item['offer']}")

    if result["errors"]:
        print(f"\nErrors: {len(result['errors'])}")
        for err in result["errors"][:5]:
            print(f"  - {err}")

    print(f"\nIngestion complete!")


if __name__ == "__main__":
    main()
