#!/usr/bin/env python3
"""
Daily CRM -> Database sync script.

Scheduled to run at 13:00 GMT+5 (08:00 UTC) daily.
Syncs sales from SALES_KSP_CRM_V3.xlsx to sales_fact_v2 and fact_sales.

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

from core.ingest.sales_ingest import (
    ingest_sales,
    ingest_sales_to_fact_sales,
    parse_sales_excel,
    resolve_sales_identity,
)
from core.db import get_db


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
    parser.add_argument("--no-reconcile", action="store_true",
                        help="Skip removing DB rows missing from current CRM date range")
    parser.add_argument("--skip-fact-sales", action="store_true",
                        help="Skip updating fact_sales from CRM")
    parser.add_argument("--skip-aggregates", action="store_true",
                        help="Skip rebuilding fact_sales_daily aggregates")
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

    if not args.no_reconcile:
        records = parse_sales_excel(str(args.file), args.sheet)
        if not records:
            print("ERROR: No CRM records found; aborting reconcile.")
            sys.exit(1)

        dates = []
        for row in records:
            dates.append(row.get("order_date"))

        min_date = min(dates)
        max_date = max(dates)
        print(f"\nReconciling sales_fact_v2 for {min_date} → {max_date}...")

        with get_db() as conn:
            crm_keys = set()
            for row in records:
                sku_key, _sku_id, my_size = resolve_sales_identity(
                    conn,
                    row.get("sku_id"),
                    row.get("sku_key"),
                    row.get("my_size"),
                    row.get("kaspi_offer_name"),
                    row.get("store_code"),
                )
                crm_keys.add((
                    str(row.get("order_id") or ""),
                    str(row.get("store_code") or ""),
                    str(row.get("kaspi_offer_name") or ""),
                    str(sku_key or ""),
                    str(my_size or ""),
                ))

            existing = conn.execute(
                """
                SELECT sale_id, order_id, store_code, kaspi_offer_name, sku_key, my_size
                FROM sales_fact_v2
                WHERE order_date BETWEEN ? AND ?
                """,
                (min_date, max_date),
            ).fetchall()
            stale_ids = []
            for row in existing:
                key = (
                    str(row["order_id"]),
                    str(row["store_code"]),
                    str(row["kaspi_offer_name"] or ""),
                    str(row["sku_key"] or ""),
                    str(row["my_size"] or ""),
                )
                if key not in crm_keys:
                    stale_ids.append(row["sale_id"])

            if stale_ids:
                print(f"Removing {len(stale_ids)} stale rows from sales_fact_v2...")
                chunk = 500
                for i in range(0, len(stale_ids), chunk):
                    batch = stale_ids[i:i + chunk]
                    placeholders = ",".join("?" for _ in batch)
                    conn.execute(
                        f"DELETE FROM sales_fact_v2 WHERE sale_id IN ({placeholders})",
                        batch,
                    )
                conn.commit()
            else:
                print("No stale rows detected in CRM date range.")

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

    print(f"\nSync Results (sales_fact_v2):")
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

    if not args.skip_fact_sales:
        print("\nSyncing fact_sales from CRM...")
        fact_result = ingest_sales_to_fact_sales(
            xlsx_path=str(args.file),
            sheet_name=args.sheet,
            dry_run=args.dry_run,
            source_file=args.file.name,
        )
        print(f"  fact_sales inserted: {fact_result.get('inserted', 0)}")
        print(f"  fact_sales updated: {fact_result.get('updated', 0)}")
        if fact_result.get("errors"):
            print(f"  fact_sales errors: {len(fact_result['errors'])}")

        if not args.skip_aggregates and fact_result.get("min_date") and fact_result.get("max_date"):
            print("\nRebuilding fact_sales_daily aggregates...")
            from scripts.build_daily_aggregates import build_all_aggregates
            build_all_aggregates(
                from_date=fact_result["min_date"],
                to_date=fact_result["max_date"],
                dry_run=args.dry_run,
                verbose=True,
            )

    print(f"\n{'=' * 60}")
    print(f"Sync complete!")


if __name__ == "__main__":
    main()
