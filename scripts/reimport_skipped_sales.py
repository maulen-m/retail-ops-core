#!/usr/bin/env python3
"""
After dim_sku is fixed, re-import sales that were skipped due to missing COGS.
Only imports records where SKU now has valid COGS.

Run: python scripts/reimport_skipped_sales.py [--dry-run]

TASK-072
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime
import argparse

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"
EXCEL_PATH = PROJECT_ROOT / "excel_ui" / "SALES_KSP_CRM_GPT_15.9.25.xlsx"


def reimport_skipped(dry_run: bool = False):
    # Load Excel data
    df = pd.read_excel(EXCEL_PATH, sheet_name='Archive_sales', header=0)
    print(f"Loaded {len(df)} rows from Archive_sales")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get SKUs that NOW have valid COGS
    cursor.execute("""
        SELECT sku_key, cogs_kzt
        FROM dim_sku
        WHERE cogs_kzt > 0
    """)
    valid_skus = dict(cursor.fetchall())
    print(f"SKUs with valid COGS: {len(valid_skus)}")

    # Get existing order_ids in fact_sales
    cursor.execute("SELECT DISTINCT order_id FROM fact_sales")
    existing_orders = set(row[0] for row in cursor.fetchall())
    print(f"Existing orders in fact_sales: {len(existing_orders)}")

    # Find rows that should now be importable
    df['has_cogs'] = df['SKU_key'].map(lambda x: x in valid_skus if pd.notna(x) else False)
    df['already_imported'] = df['OrderID'].astype(str).map(lambda x: x in existing_orders)

    candidates = df[df['has_cogs'] & ~df['already_imported']]
    print(f"Candidates for re-import: {len(candidates)}")

    if len(candidates) == 0:
        print("No new records to import - all eligible records are already in fact_sales")
        conn.close()
        return

    if dry_run:
        print("\n[DRY RUN] Would import these records:")
        print(candidates[['OrderID', 'SKU_key', 'Quantity']].head(20).to_string(index=False))
        conn.close()
        return

    # Import candidates using the rebuild_fact_sales logic
    # For now, we just report - actual import uses rebuild_fact_sales.py
    print(f"\nTo import these records, run:")
    print(f"  python scripts/rebuild_fact_sales.py")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Re-import skipped sales')
    parser.add_argument('--dry-run', action='store_true', help='Preview without importing')
    args = parser.parse_args()

    reimport_skipped(args.dry_run)


if __name__ == "__main__":
    main()
