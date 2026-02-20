#!/usr/bin/env python3
"""
Sync current stock from Excel file to database.

Updates fact_inventory_snapshot_size with hardened stock data.
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"


def sync_stock_from_excel(excel_path: str, snapshot_date: str = None):
    """Load stock data from Excel and update database."""

    print(f"Reading Excel file: {excel_path}")
    df = pd.read_excel(excel_path)

    # Use date from file or override
    if snapshot_date is None:
        snapshot_date = df['Data_date'].iloc[0].strftime('%Y-%m-%d')

    print(f"Snapshot date: {snapshot_date}")
    print(f"Total rows: {len(df)}")

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Delete existing snapshot for this date
    cursor.execute("""
        DELETE FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
    """, (snapshot_date,))
    deleted = cursor.rowcount
    print(f"Deleted {deleted} existing rows for {snapshot_date}")

    # Insert new snapshot data
    inserted = 0
    for _, row in df.iterrows():
        sku_id = row['SKU_ID']
        sku_key = row['SKU_key']
        my_size = str(row['MY_SIZE'])
        current_stock = int(row['Current_stock'])
        inbound_stock = int(row['Inbound_stock']) if pd.notna(row['Inbound_stock']) else 0

        # Skip rows with size '0' (these are invalid)
        if my_size == '0' or my_size == 'nan':
            continue

        cursor.execute("""
            INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock))
        inserted += 1

    conn.commit()
    print(f"Inserted {inserted} stock rows")

    # Verify
    cursor.execute("""
        SELECT COUNT(*), SUM(current_stock), SUM(inbound_stock)
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
    """, (snapshot_date,))
    count, total_stock, total_inbound = cursor.fetchone()
    print(f"\nVerification for {snapshot_date}:")
    print(f"  Rows: {count}")
    print(f"  Total stock: {total_stock}")
    print(f"  Total inbound: {total_inbound or 0}")

    # Show top SKUs by stock
    cursor.execute("""
        SELECT sku_key, my_size, current_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        ORDER BY current_stock DESC
        LIMIT 10
    """, (snapshot_date,))
    print("\nTop 10 by stock:")
    for row in cursor.fetchall():
        print(f"  {row[0]} / {row[1]}: {row[2]}")

    conn.close()
    return snapshot_date


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sync_current_stock.py <excel_path> [snapshot_date]")
        print("Example: python sync_current_stock.py excel/stock.xlsx 2025-12-13")
        sys.exit(1)

    excel_path = sys.argv[1]
    snapshot_date = sys.argv[2] if len(sys.argv) > 2 else None

    sync_stock_from_excel(excel_path, snapshot_date)
