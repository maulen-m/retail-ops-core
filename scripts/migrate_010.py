#!/usr/bin/env python3
"""
Migration 010: Add multi-channel support for Phase 8.

Creates:
- dim_channel: Channel configuration and fee structures
- fact_channel_metrics: Daily + rolling metrics per SKU per channel
- fact_channel_inventory: Stock levels per channel
- fact_expansion_scores: Expansion potential scores
- Updates dim_store with channel_code FK
- Adds WB FBO store

TASK-085, TASK-086, TASK-087, TASK-088, TASK-092
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def migrate():
    """Run migration 010."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("Migration 010: Adding multi-channel support")
    print("=" * 60)

    # =========================================================================
    # TASK-085: Create dim_channel table
    # =========================================================================
    print("\n[TASK-085] Creating dim_channel table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_channel (
            channel_code TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL,

            -- Fee structure
            commission_pct REAL NOT NULL,        -- 12.5 for Kaspi, 24.5 for WB
            vat_pct REAL NOT NULL,               -- 3.0 (both)
            logistics_fee_rub REAL DEFAULT 0,    -- 408 for WB clothes (Line52/Line51 proxy)
                                                 -- NOTE: This is a weighted avg. Actual WB fees vary by:
                                                 -- product size, weight, warehouse, return rate.
                                                 -- Phase 9+ will add per-SKU fee calculation.

            -- Delivery fee tiers (Kaspi only)
            dlv_tier1_max INTEGER DEFAULT 0,     -- 4999
            dlv_tier1_fee INTEGER DEFAULT 0,     -- 0
            dlv_tier2_max INTEGER DEFAULT 0,     -- 14999
            dlv_tier2_fee INTEGER DEFAULT 0,     -- 856
            dlv_tier3_fee INTEGER DEFAULT 0,     -- 1259

            -- Payment terms
            payment_delay_days INTEGER NOT NULL, -- 2 for Kaspi, 11 for WB
            payment_cycle_days INTEGER DEFAULT 1,-- 1 for Kaspi, 7 for WB

            -- Lead times (for inventory planning)
            l3_days INTEGER DEFAULT 0,           -- Astana→Channel warehouse
            default_safety_buffer INTEGER DEFAULT 14,
            default_reorder_cycle INTEGER DEFAULT 10,

            -- FX (for non-KZT channels)
            currency_code TEXT DEFAULT 'KZT',
            fx_rate_to_kzt REAL DEFAULT 1.0,

            -- Metadata
            active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed Kaspi channel
    cursor.execute("""
        INSERT OR REPLACE INTO dim_channel (
            channel_code, channel_name,
            commission_pct, vat_pct, logistics_fee_rub,
            dlv_tier1_max, dlv_tier1_fee, dlv_tier2_max, dlv_tier2_fee, dlv_tier3_fee,
            payment_delay_days, payment_cycle_days,
            l3_days, default_safety_buffer, default_reorder_cycle,
            currency_code, fx_rate_to_kzt,
            active, notes
        ) VALUES (
            'KSP', 'Kaspi.kz',
            12.5, 3.0, 0,
            4999, 0, 14999, 856, 1259,
            2, 1,
            0, 7, 10,
            'KZT', 1.0,
            1, 'Primary channel - Kazakhstan marketplace'
        )
    """)

    # Seed WB channel
    cursor.execute("""
        INSERT OR REPLACE INTO dim_channel (
            channel_code, channel_name,
            commission_pct, vat_pct, logistics_fee_rub,
            dlv_tier1_max, dlv_tier1_fee, dlv_tier2_max, dlv_tier2_fee, dlv_tier3_fee,
            payment_delay_days, payment_cycle_days,
            l3_days, default_safety_buffer, default_reorder_cycle,
            currency_code, fx_rate_to_kzt,
            active, notes
        ) VALUES (
            'WB', 'Wildberries',
            24.5, 3.0, 408,
            0, 0, 0, 0, 0,
            11, 7,
            10, 14, 10,
            'RUB', 6.6,
            1, 'Russia expansion - FBO model. Logistics fee is weighted avg for Line52/Line51.'
        )
    """)

    print("  - dim_channel created and seeded (KSP, WB)")

    # =========================================================================
    # TASK-092: Update dim_store channel values and create WB store
    # =========================================================================
    print("\n[TASK-092] Updating dim_store for multi-channel support...")

    cursor.execute("PRAGMA table_info(dim_store)")
    columns = [row[1] for row in cursor.fetchall()]

    # The existing column is 'channel', update it to use our codes
    if 'channel' in columns:
        cursor.execute("""
            UPDATE dim_store SET channel = 'KSP'
            WHERE channel = 'kaspi' OR channel IS NULL
        """)
        print("  - Updated existing stores to channel='KSP'")

    # Add WB FBO store using actual schema
    # Schema: store_code, channel, region, active_flag
    cursor.execute("""
        INSERT OR REPLACE INTO dim_store (
            store_code, channel, region, active_flag
        ) VALUES (
            'wb_fbo', 'WB', 'Russia', 1
        )
    """)
    print("  - Added WB FBO store")

    # =========================================================================
    # TASK-086: Create fact_channel_metrics table
    # =========================================================================
    print("\n[TASK-086] Creating fact_channel_metrics table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_channel_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            channel_code TEXT NOT NULL,
            store_code TEXT NOT NULL,

            -- Volume metrics
            units_sold INTEGER DEFAULT 0,
            units_returned INTEGER DEFAULT 0,
            net_units INTEGER DEFAULT 0,

            -- Revenue metrics (in KZT)
            gross_revenue_kzt REAL DEFAULT 0,
            net_revenue_kzt REAL DEFAULT 0,
            cogs_kzt REAL DEFAULT 0,
            profit_kzt REAL DEFAULT 0,

            -- Derived metrics
            avg_selling_price_kzt REAL DEFAULT 0,
            margin_pct REAL DEFAULT 0,
            return_rate_pct REAL DEFAULT 0,

            -- Rolling metrics (30-day)
            units_30d INTEGER DEFAULT 0,
            revenue_30d_kzt REAL DEFAULT 0,
            profit_30d_kzt REAL DEFAULT 0,
            roic_30d_pct REAL DEFAULT 0,

            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (sku_key) REFERENCES dim_sku(sku_key),
            FOREIGN KEY (channel_code) REFERENCES dim_channel(channel_code),
            FOREIGN KEY (store_code) REFERENCES dim_store(store_code),
            UNIQUE(metric_date, sku_key, channel_code, store_code)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_metrics_date
        ON fact_channel_metrics(metric_date)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_metrics_sku_channel
        ON fact_channel_metrics(sku_key, channel_code)
    """)

    print("  - fact_channel_metrics created with indexes")

    # =========================================================================
    # TASK-087: Create fact_channel_inventory table
    # =========================================================================
    print("\n[TASK-087] Creating fact_channel_inventory table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_channel_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            channel_code TEXT NOT NULL,
            store_code TEXT NOT NULL,

            -- Stock levels
            on_hand_units INTEGER DEFAULT 0,
            on_order_units INTEGER DEFAULT 0,
            in_transit_units INTEGER DEFAULT 0,
            total_available INTEGER DEFAULT 0,

            -- Inventory health
            days_of_cover REAL DEFAULT 0,
            stockout_risk TEXT DEFAULT 'LOW',  -- LOW, MEDIUM, HIGH, CRITICAL

            -- Capital deployed
            inventory_value_kzt REAL DEFAULT 0,

            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (sku_key) REFERENCES dim_sku(sku_key),
            FOREIGN KEY (channel_code) REFERENCES dim_channel(channel_code),
            UNIQUE(snapshot_date, sku_key, channel_code, store_code)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_inventory_date
        ON fact_channel_inventory(snapshot_date)
    """)

    print("  - fact_channel_inventory created with index")

    # =========================================================================
    # TASK-088: Create fact_expansion_scores table
    # =========================================================================
    print("\n[TASK-088] Creating fact_expansion_scores table...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_expansion_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            score_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            source_channel TEXT NOT NULL,      -- Where SKU currently sells
            target_channel TEXT NOT NULL,      -- Where we're evaluating expansion

            -- Source channel performance
            source_d30 REAL DEFAULT 0,
            source_roic_pct REAL DEFAULT 0,
            source_margin_pct REAL DEFAULT 0,
            source_avg_price_kzt REAL DEFAULT 0,

            -- Target channel potential
            target_price_rub REAL DEFAULT 0,
            target_est_margin_pct REAL DEFAULT 0,
            target_est_roic_pct REAL DEFAULT 0,
            margin_headroom_pct REAL DEFAULT 0,

            -- Competitive analysis
            competition_density INTEGER DEFAULT 0,  -- # of competitors
            price_position TEXT DEFAULT 'UNKNOWN',  -- PREMIUM, MID, VALUE

            -- Scoring
            demand_score REAL DEFAULT 0,       -- 0-100
            margin_score REAL DEFAULT 0,       -- 0-100
            competition_score REAL DEFAULT 0,  -- 0-100
            expansion_score REAL DEFAULT 0,    -- Weighted composite 0-100

            -- Recommendation
            recommendation TEXT DEFAULT 'HOLD',  -- EXPAND, TEST, HOLD, SKIP
            confidence TEXT DEFAULT 'LOW',       -- LOW, MEDIUM, HIGH
            notes TEXT,

            -- Metadata
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (sku_key) REFERENCES dim_sku(sku_key),
            UNIQUE(score_date, sku_key, target_channel)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_expansion_scores_date
        ON fact_expansion_scores(score_date)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_expansion_scores_sku
        ON fact_expansion_scores(sku_key)
    """)

    print("  - fact_expansion_scores created with indexes")

    # =========================================================================
    # Add channel_code to fact_sales if not exists
    # =========================================================================
    print("\n[Extra] Checking fact_sales for channel_code column...")

    cursor.execute("PRAGMA table_info(fact_sales)")
    fact_sales_columns = [row[1] for row in cursor.fetchall()]

    if 'channel_code' not in fact_sales_columns:
        cursor.execute("""
            ALTER TABLE fact_sales ADD COLUMN channel_code TEXT DEFAULT 'KSP'
        """)
        cursor.execute("""
            UPDATE fact_sales SET channel_code = 'KSP' WHERE channel_code IS NULL
        """)
        print("  - Added channel_code column to fact_sales")
    else:
        print("  - channel_code column already exists in fact_sales")

    # =========================================================================
    # Commit and verify
    # =========================================================================
    conn.commit()

    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    # Verify channels
    cursor.execute("SELECT channel_code, channel_name, commission_pct, currency_code FROM dim_channel")
    channels = cursor.fetchall()
    print(f"\nChannels configured: {len(channels)}")
    for ch in channels:
        print(f"  {ch[0]}: {ch[1]} ({ch[2]}% commission, {ch[3]})")

    # Verify stores
    cursor.execute("SELECT store_code, channel, region FROM dim_store WHERE channel = 'WB'")
    wb_stores = cursor.fetchall()
    print(f"\nWB stores: {len(wb_stores)}")
    for st in wb_stores:
        print(f"  {st[0]}: region={st[2]} (channel: {st[1]})")

    # Verify tables
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name IN (
            'dim_channel', 'fact_channel_metrics',
            'fact_channel_inventory', 'fact_expansion_scores'
        )
    """)
    tables = [row[0] for row in cursor.fetchall()]
    print(f"\nNew tables created: {len(tables)}")
    for t in tables:
        print(f"  - {t}")

    conn.close()

    print("\n" + "=" * 60)
    print("Migration 010 complete!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
