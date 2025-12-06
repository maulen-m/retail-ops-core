#!/usr/bin/env python3
"""
Migration 011: Add Kaspi order tracking table for Phase 9.5.

Creates:
- fact_orders_kaspi: Order lifecycle tracking for Kaspi orders
  Tracks orders from NEW through SHIPPED/COMPLETED/CANCELLED
  Distinct from fact_sales_raw (which captures completed sales)

TASK-114: Phase 9.5 Kaspi Order Automation
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def migrate():
    """Run migration 011."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("Migration 011: Adding Kaspi order tracking")
    print("=" * 60)

    # =========================================================================
    # TASK-114: Create fact_orders_kaspi table
    # =========================================================================
    print("\n[TASK-114] Creating fact_orders_kaspi table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            channel_code TEXT DEFAULT 'KSP',

            -- Order details
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price_kzt REAL,

            -- Dates
            created_at TEXT,
            planned_shipment_date TEXT,
            actual_shipment_date TEXT,

            -- Status tracking
            kaspi_status TEXT,           -- Raw Kaspi status (Russian)
            internal_status TEXT DEFAULT 'NEW',  -- NEW, READY, SHIPPED, COMPLETED, CANCELLED
            status_updated_at TEXT,

            -- Waybill info
            waybill_url TEXT,
            waybill_number TEXT,
            waybill_downloaded INTEGER DEFAULT 0,

            -- Audit
            source TEXT DEFAULT 'EXCEL_EXPORT',  -- EXCEL_EXPORT, API
            source_file TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            -- Dedup key: handles multi-line orders correctly
            UNIQUE(order_id, sku_id, store_code)
        )
    """)

    print("  - fact_orders_kaspi created")

    # Create indexes for common query patterns
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_kaspi_status
        ON fact_orders_kaspi(internal_status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_kaspi_date
        ON fact_orders_kaspi(planned_shipment_date)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_kaspi_store
        ON fact_orders_kaspi(store_code)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_kaspi_order_id
        ON fact_orders_kaspi(order_id)
    """)

    print("  - Indexes created: status, date, store, order_id")

    # =========================================================================
    # Create trigger to update updated_at on row changes
    # =========================================================================
    print("\n[Extra] Creating update trigger...")

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_orders_kaspi_updated
        AFTER UPDATE ON fact_orders_kaspi
        FOR EACH ROW
        BEGIN
            UPDATE fact_orders_kaspi
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END
    """)

    print("  - Update trigger created")

    # =========================================================================
    # Commit and verify
    # =========================================================================
    conn.commit()

    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # Verify table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name = 'fact_orders_kaspi'
    """)
    table = cursor.fetchone()
    if table:
        print(f"\n  Table created: {table[0]}")

    # Verify columns
    cursor.execute("PRAGMA table_info(fact_orders_kaspi)")
    columns = cursor.fetchall()
    print(f"  Columns: {len(columns)}")
    for col in columns:
        print(f"    - {col[1]} ({col[2]})")

    # Verify indexes
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND tbl_name = 'fact_orders_kaspi'
    """)
    indexes = cursor.fetchall()
    print(f"\n  Indexes: {len(indexes)}")
    for idx in indexes:
        print(f"    - {idx[0]}")

    conn.close()

    print("\n" + "=" * 60)
    print("Migration 011 complete!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
