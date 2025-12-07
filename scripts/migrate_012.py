#!/usr/bin/env python3
"""
Migration 012: Size Probability Engine (Phase 9.5 Part 2).

Creates:
- dim_size_probability: Stores size mode statistics at offer/style/product-type levels
- Size columns on fact_orders_kaspi: assigned_size, size_source, size_confidence

TASK-135: Create dim_size_probability table
TASK-138: Add size columns to fact_orders_kaspi
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def migrate():
    """Run migration 012."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("Migration 012: Size Probability Engine")
    print("=" * 60)

    # =========================================================================
    # TASK-135: Create dim_size_probability table
    # =========================================================================
    print("\n[TASK-135] Creating dim_size_probability table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_size_probability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,               -- 'OFFER' | 'STYLE' | 'PRODUCT_TYPE'
            key_value TEXT NOT NULL,           -- kaspi_offer_name | sku_key | product_type
            mode_size TEXT NOT NULL,           -- Most frequent size (e.g., 'L', 'XL')
            mode_share REAL NOT NULL,          -- Percentage (0.0-1.0)
            sample_count INTEGER NOT NULL,     -- Number of observations
            confidence TEXT NOT NULL,          -- 'HIGH' (≥60%) | 'MEDIUM' (40-60%) | 'LOW' (<40%)
            size_distribution TEXT,            -- JSON: {"S": 0.1, "M": 0.2, "L": 0.4, ...}
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(level, key_value)
        )
    """)
    print("  - dim_size_probability created")

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_size_prob_level
        ON dim_size_probability(level)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_size_prob_key
        ON dim_size_probability(key_value)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_size_prob_confidence
        ON dim_size_probability(confidence)
    """)
    print("  - Indexes created: level, key_value, confidence")

    # Create update trigger
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_size_prob_updated
        AFTER UPDATE ON dim_size_probability
        FOR EACH ROW
        BEGIN
            UPDATE dim_size_probability
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END
    """)
    print("  - Update trigger created")

    # =========================================================================
    # TASK-138: Add size columns to fact_orders_kaspi
    # =========================================================================
    print("\n[TASK-138] Adding size columns to fact_orders_kaspi...")

    # Check existing columns
    cursor.execute("PRAGMA table_info(fact_orders_kaspi)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("assigned_size", "TEXT", "Determined size for the order"),
        ("size_source", "TEXT", "'CUSTOMER' | 'OFFER_MODE' | 'STYLE_MODE' | 'DEFAULT'"),
        ("size_confidence", "TEXT", "'HIGH' | 'MEDIUM' | 'LOW'"),
        ("customer_height_cm", "INTEGER", "Customer provided height"),
        ("customer_weight_kg", "INTEGER", "Customer provided weight"),
    ]

    for col_name, col_type, comment in new_columns:
        if col_name not in existing_columns:
            cursor.execute(f"""
                ALTER TABLE fact_orders_kaspi
                ADD COLUMN {col_name} {col_type}
            """)
            print(f"  - Added column: {col_name} ({col_type})")
        else:
            print(f"  - Column already exists: {col_name}")

    # Create index on size_source for filtering
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_kaspi_size_source
        ON fact_orders_kaspi(size_source)
    """)
    print("  - Index created: size_source")

    # =========================================================================
    # Seed default product type sizes
    # =========================================================================
    print("\n[Extra] Seeding default product type sizes...")

    defaults = [
        ('PRODUCT_TYPE', 'CL', 'L', 0.35, 100, 'MEDIUM', '{"S": 0.10, "M": 0.25, "L": 0.35, "XL": 0.20, "2XL": 0.08, "3XL": 0.02}'),
        ('PRODUCT_TYPE', 'ELS', 'M', 0.40, 50, 'MEDIUM', '{"S": 0.15, "M": 0.40, "L": 0.30, "XL": 0.12, "2XL": 0.03}'),
        ('PRODUCT_TYPE', 'FUR', 'L', 0.30, 30, 'LOW', '{"S": 0.08, "M": 0.22, "L": 0.30, "XL": 0.25, "2XL": 0.12, "3XL": 0.03}'),
        ('PRODUCT_TYPE', 'KIDS', '28', 0.25, 20, 'LOW', '{"24": 0.15, "26": 0.20, "28": 0.25, "30": 0.20, "32": 0.15, "34": 0.05}'),
    ]

    for level, key_value, mode_size, mode_share, sample_count, confidence, distribution in defaults:
        cursor.execute("""
            INSERT OR IGNORE INTO dim_size_probability
            (level, key_value, mode_size, mode_share, sample_count, confidence, size_distribution)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (level, key_value, mode_size, mode_share, sample_count, confidence, distribution))

    print("  - Seeded 4 product type defaults")

    # =========================================================================
    # Commit and verify
    # =========================================================================
    conn.commit()

    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # Verify dim_size_probability
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name = 'dim_size_probability'
    """)
    table = cursor.fetchone()
    if table:
        print(f"\n  Table created: {table[0]}")

    cursor.execute("PRAGMA table_info(dim_size_probability)")
    columns = cursor.fetchall()
    print(f"  Columns: {len(columns)}")

    cursor.execute("SELECT COUNT(*) FROM dim_size_probability")
    count = cursor.fetchone()[0]
    print(f"  Default records: {count}")

    # Verify fact_orders_kaspi columns
    cursor.execute("PRAGMA table_info(fact_orders_kaspi)")
    columns = cursor.fetchall()
    size_columns = [col[1] for col in columns if 'size' in col[1].lower() or 'customer' in col[1].lower()]
    print(f"\n  Size columns in fact_orders_kaspi: {size_columns}")

    conn.close()

    print("\n" + "=" * 60)
    print("Migration 012 complete!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
