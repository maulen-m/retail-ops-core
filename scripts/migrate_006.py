#!/usr/bin/env python3
"""
Migration 006: Add kaspi_offer_name and my_size columns for Phase 6.5 rebuild.

Adds:
- kaspi_offer_name to fact_sales (for order line traceability)
- my_size to fact_sales (for size-level tracking)
- sku_key, my_size, revenue, cogs, profit to fact_sales_daily_size

Run: python3 scripts/migrate_006.py
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def add_column_if_not_exists(cursor: sqlite3.Cursor, table: str, column: str, dtype: str):
    """Add column to table if it doesn't already exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]

    if column not in columns:
        print(f"  Adding {column} to {table}...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {dtype}")
        return True
    else:
        print(f"  ✓ {column} already exists in {table}")
        return False


def migrate():
    """Run migration 006."""
    print("="*60)
    print("Migration 006: Add columns for Phase 6.5 rebuild")
    print(f"Started: {datetime.now()}")
    print("="*60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    changes = 0

    # fact_sales columns
    print("\nfact_sales:")
    if add_column_if_not_exists(cursor, "fact_sales", "kaspi_offer_name", "TEXT"):
        changes += 1
    if add_column_if_not_exists(cursor, "fact_sales", "my_size", "TEXT"):
        changes += 1

    # fact_sales_raw columns (if table exists)
    print("\nfact_sales_raw:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fact_sales_raw'")
    if cursor.fetchone():
        if add_column_if_not_exists(cursor, "fact_sales_raw", "kaspi_offer_name", "TEXT"):
            changes += 1
    else:
        print("  (table does not exist, skipping)")

    # fact_sales_daily_size columns
    print("\nfact_sales_daily_size:")
    if add_column_if_not_exists(cursor, "fact_sales_daily_size", "sku_key", "TEXT"):
        changes += 1
    if add_column_if_not_exists(cursor, "fact_sales_daily_size", "my_size", "TEXT"):
        changes += 1
    if add_column_if_not_exists(cursor, "fact_sales_daily_size", "revenue", "REAL DEFAULT 0"):
        changes += 1
    if add_column_if_not_exists(cursor, "fact_sales_daily_size", "cogs", "REAL DEFAULT 0"):
        changes += 1
    if add_column_if_not_exists(cursor, "fact_sales_daily_size", "profit", "REAL DEFAULT 0"):
        changes += 1

    conn.commit()
    conn.close()

    print("\n" + "="*60)
    print(f"Migration 006 complete: {changes} columns added")
    print(f"Finished: {datetime.now()}")
    print("="*60)


if __name__ == "__main__":
    migrate()
