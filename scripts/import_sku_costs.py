#!/usr/bin/env python3
"""
Import SKU cost data from Inventory_Core_V15_FINAL.xlsx Dim_SKU sheet.
Updates dim_sku with base_cost_cny, weight_kg, cogs_kzt.

Data source: excel/Inventory_Core_V15_FINAL.xlsx → Dim_SKU
Contains 54 SKUs with complete cost data.

Run: python scripts/import_sku_costs.py [--dry-run]

TASK-071
"""
import sqlite3
import pandas as pd
from pathlib import Path
import argparse
import sys

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"
EXCEL_PATH = Path(__file__).parent.parent / "excel" / "Inventory_Core_V15_FINAL.xlsx"


def import_costs(dry_run: bool = False):
    """Import cost data from Inventory_Core Dim_SKU sheet."""

    # Load from Inventory_Core
    print(f"Loading from {EXCEL_PATH}...")
    df = pd.read_excel(EXCEL_PATH, sheet_name='Dim_SKU', header=0)

    # Rename columns to match our schema
    df = df.rename(columns={
        'SKU_key': 'sku_key',
        'Weight_kg': 'weight_kg',
        'BaseCost_CNY': 'base_cost_cny',
        'COGS': 'cogs_kzt'
    })

    # Validate required columns exist
    required_cols = ['sku_key', 'base_cost_cny', 'weight_kg', 'cogs_kzt']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        print(f"ERROR: Missing columns: {missing}")
        sys.exit(1)

    # Filter to rows with valid data
    df = df[df['base_cost_cny'] > 0]

    print(f"Loaded {len(df)} SKUs with valid cost data")
    print(f"\nSample COGS calculations:")
    print(df[['sku_key', 'base_cost_cny', 'weight_kg', 'cogs_kzt']].head(10).to_string(index=False))

    if dry_run:
        print("\n[DRY RUN] Would update these SKUs in dim_sku")
        return

    # Update database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updated = 0
    inserted = 0

    for _, row in df.iterrows():
        # First try to update existing SKU
        cursor.execute("""
            UPDATE dim_sku
            SET base_cost_cny = ?,
                weight_kg = ?,
                cogs_kzt = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE sku_key = ?
        """, (row['base_cost_cny'], row['weight_kg'], row['cogs_kzt'], row['sku_key']))

        if cursor.rowcount > 0:
            updated += 1
        else:
            # SKU doesn't exist in dim_sku, insert it
            # Extract product_type, model, color from sku_key
            sku_parts = row['sku_key'].split('_')
            product_type = sku_parts[0] if sku_parts else 'CL'

            # Determine model and color
            if len(sku_parts) >= 4:
                model = sku_parts[-2]
                color = sku_parts[-1]
            else:
                model = row['sku_key']
                color = None

            cursor.execute("""
                INSERT INTO dim_sku (sku_key, model, color, product_type, base_cost_cny, weight_kg, cogs_kzt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (row['sku_key'], model, color, product_type,
                  row['base_cost_cny'], row['weight_kg'], row['cogs_kzt']))

            if cursor.rowcount > 0:
                inserted += 1

    conn.commit()
    conn.close()

    print(f"\n✓ Updated {updated} SKUs in dim_sku")
    print(f"✓ Inserted {inserted} new SKUs into dim_sku")
    print(f"Total: {updated + inserted} SKUs processed")


def main():
    parser = argparse.ArgumentParser(description='Import SKU cost data')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    args = parser.parse_args()

    if not EXCEL_PATH.exists():
        print(f"ERROR: File not found: {EXCEL_PATH}")
        sys.exit(1)

    import_costs(args.dry_run)


if __name__ == "__main__":
    main()
