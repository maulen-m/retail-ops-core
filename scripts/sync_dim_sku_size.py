#!/usr/bin/env python3
"""
Sync dim_sku_size from stock file.
Adds missing SKU+size combinations to the dimension table.

Usage:
    python scripts/sync_dim_sku_size.py <stock_file.xlsx> [--dry-run]
"""
import sqlite3
import pandas as pd
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"

# Size order mapping
SIZE_ORDER = {
    'XS': 1, 'S': 2, 'M': 3, 'L': 4, 'XL': 5, '2XL': 6, '3XL': 7, '4XL': 8, '5XL': 9,
    '22': 10, '24': 11, '26': 12, '28': 13, '30': 14, '32': 15, '34': 16,
    'ONE_SIZE': 100, 'ONESIZE': 100, 'OS': 100, '0': 100
}

def sync_dim_sku_size(stock_file: str, dry_run: bool = False):
    """Sync dim_sku_size from stock file."""

    # Read stock file
    df = pd.read_excel(stock_file, engine='openpyxl')
    print(f"Read {len(df)} rows from {stock_file}")

    # Get existing dim_sku_size entries
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    existing = set()
    for row in conn.execute("SELECT sku_id FROM dim_sku_size"):
        existing.add(row['sku_id'])

    print(f"Existing dim_sku_size entries: {len(existing)}")

    # Electronics product type prefixes (no size needed)
    ELECTRONICS_PREFIXES = ('ELS_', 'ELEC_', 'ELECTRONICS_')

    # Find missing entries
    to_insert = []
    for _, row in df.iterrows():
        sku_key = row.get('SKU_key') or row.get('sku_key')
        my_size = row.get('MY_SIZE') or row.get('my_size')
        sku_id = row.get('SKU_ID') or row.get('sku_id')

        if pd.isna(sku_key):
            continue

        sku_key = str(sku_key).strip()

        # Handle missing size
        if pd.isna(my_size) or str(my_size).strip() in ('nan', 'NaN', '', '0'):
            # Electronics/printers get ONE_SIZE
            if any(sku_key.upper().startswith(prefix) for prefix in ELECTRONICS_PREFIXES):
                my_size = 'ONE_SIZE'
            else:
                continue  # Skip non-electronics without size

        my_size = str(my_size).strip()

        # Build sku_id if not provided
        if pd.isna(sku_id):
            sku_id = f"{sku_key}_{my_size}"

        if sku_id not in existing:
            size_order = SIZE_ORDER.get(my_size, 50)
            to_insert.append({
                'sku_id': sku_id,
                'sku_key': sku_key,
                'my_size': my_size,
                'barcode': '',
                'size_order': size_order,
                'active_flag': 1
            })
            existing.add(sku_id)  # Avoid duplicates in same run

    print(f"Missing entries to add: {len(to_insert)}")

    if to_insert:
        print("\nSample entries:")
        for entry in to_insert[:10]:
            print(f"  {entry['sku_id']}: {entry['sku_key']} / {entry['my_size']}")
        if len(to_insert) > 10:
            print(f"  ... and {len(to_insert) - 10} more")

    if dry_run:
        print("\n[DRY RUN] No changes made")
        conn.close()
        return len(to_insert)

    # Insert missing entries
    cursor = conn.cursor()
    for entry in to_insert:
        cursor.execute("""
            INSERT OR IGNORE INTO dim_sku_size
            (sku_id, sku_key, my_size, barcode, size_order, active_flag)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry['sku_id'],
            entry['sku_key'],
            entry['my_size'],
            entry['barcode'],
            entry['size_order'],
            entry['active_flag']
        ))

    conn.commit()

    # Verify
    count = conn.execute("SELECT COUNT(*) FROM dim_sku_size").fetchone()[0]
    print(f"\nTotal dim_sku_size entries after sync: {count}")

    conn.close()
    print("Done!")
    return len(to_insert)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/sync_dim_sku_size.py <stock_file.xlsx> [--dry-run]")
        sys.exit(1)

    stock_file = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    sync_dim_sku_size(stock_file, dry_run)
