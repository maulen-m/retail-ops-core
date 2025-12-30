#!/usr/bin/env python3
"""
Seed initial parameter rows for operational tables.

Part 3 requirement: Ensure parameter tables have valid initial data
so the system doesn't fall back to defaults silently.

Tables seeded:
- dim_fx_rates: Initial FX rates
- dim_budget_caps: Initial budget caps (optional)
- dim_params: Core inventory parameters (if not present)

Usage:
    python scripts/seed_params.py [--force]

    --force: Re-seed even if data exists
"""

import argparse
import sqlite3
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "db" / "app.db"

# Default FX rates (from Master_Inventory_Rules_v6.md)
DEFAULT_FX_RATES = {
    "cny_kzt": 78.0,
    "usd_kzt": 530.0,
    "dlv_rate_usd_kg": 2.66,
}

# Frozen inventory parameters (L=21, R=10, B=14, z=1.65, TV=0.23)
FROZEN_PARAMS = {
    "L_days": 21,           # Lead time
    "R_days": 10,           # Reorder cycle
    "B_days": 14,           # Buffer days (SS floor)
    "z_factor": 1.65,       # Safety stock z-score
    "TV_factor": 0.23,      # Size mix variability factor (CL only)
    "sigma_factor": 0.4,    # CV for sigma estimation
    "VAT_rate": 0.03,       # VAT rate (through 2025-12-31)
}


def seed_fx_rates(conn: sqlite3.Connection, force: bool = False) -> int:
    """Seed dim_fx_rates with initial values."""
    cursor = conn.cursor()

    # Check if data exists
    cursor.execute("SELECT COUNT(*) FROM dim_fx_rates")
    count = cursor.fetchone()[0]

    if count > 0 and not force:
        print(f"  dim_fx_rates: {count} rows exist, skipping (use --force to reseed)")
        return 0

    # Insert initial FX rates
    today = date.today().isoformat()
    cursor.execute("""
        INSERT OR REPLACE INTO dim_fx_rates
        (effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg, source)
        VALUES (?, ?, ?, ?, 'SEED')
    """, (
        today,
        DEFAULT_FX_RATES["cny_kzt"],
        DEFAULT_FX_RATES["usd_kzt"],
        DEFAULT_FX_RATES["dlv_rate_usd_kg"],
    ))

    print(f"  dim_fx_rates: Seeded with CNY/KZT={DEFAULT_FX_RATES['cny_kzt']}, "
          f"USD/KZT={DEFAULT_FX_RATES['usd_kzt']}, DLV={DEFAULT_FX_RATES['dlv_rate_usd_kg']}")
    return 1


def seed_params(conn: sqlite3.Connection, force: bool = False) -> int:
    """Seed dim_params with frozen inventory parameters."""
    cursor = conn.cursor()

    # Check if data exists
    cursor.execute("SELECT COUNT(*) FROM dim_params")
    count = cursor.fetchone()[0]

    if count > 0 and not force:
        print(f"  dim_params: {count} rows exist, skipping (use --force to reseed)")
        return 0

    # Insert frozen parameters
    seeded = 0
    for param_key, param_value in FROZEN_PARAMS.items():
        cursor.execute("""
            INSERT OR REPLACE INTO dim_params
            (param_key, product_type, param_value, description)
            VALUES (?, NULL, ?, ?)
        """, (
            param_key,
            param_value,
            f"Frozen parameter (Master_Inventory_Rules_v6.md)"
        ))
        seeded += 1

    print(f"  dim_params: Seeded {seeded} frozen parameters (L={FROZEN_PARAMS['L_days']}, "
          f"R={FROZEN_PARAMS['R_days']}, B={FROZEN_PARAMS['B_days']}, z={FROZEN_PARAMS['z_factor']}, "
          f"TV={FROZEN_PARAMS['TV_factor']})")
    return seeded


def seed_budget_caps(conn: sqlite3.Connection, force: bool = False) -> int:
    """Seed dim_budget_caps with initial values (optional)."""
    cursor = conn.cursor()

    # Check if data exists
    cursor.execute("SELECT COUNT(*) FROM dim_budget_caps WHERE active_flag = 1")
    count = cursor.fetchone()[0]

    if count > 0 and not force:
        print(f"  dim_budget_caps: {count} active rows exist, skipping")
        return 0

    # Insert default budget caps (unlimited by default)
    cursor.execute("""
        INSERT INTO dim_budget_caps
        (global_monthly_cap_kzt, per_draft_cap_kzt, notes)
        VALUES (0, 0, 'Initial seed - no caps (0 = unlimited)')
    """)

    print("  dim_budget_caps: Seeded with no caps (0 = unlimited)")
    return 1


def ensure_tables_exist(conn: sqlite3.Connection):
    """Create tables if they don't exist (from schema.sql definitions)."""
    cursor = conn.cursor()

    # dim_fx_rates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_fx_rates (
            effective_date TEXT PRIMARY KEY,
            cny_kzt REAL NOT NULL,
            usd_kzt REAL NOT NULL,
            dlv_rate_usd_kg REAL NOT NULL,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # dim_demand_overrides
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_demand_overrides (
            sku_key TEXT PRIMARY KEY,
            d_override REAL NOT NULL,
            reason TEXT,
            source TEXT,
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # dim_budget_caps
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_budget_caps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            global_monthly_cap_kzt REAL,
            per_draft_cap_kzt REAL,
            effective_date TEXT DEFAULT (date('now')),
            active_flag INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            notes TEXT
        )
    """)

    # dim_params (if not exists)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_params (
            param_key TEXT PRIMARY KEY,
            product_type TEXT,
            param_value REAL NOT NULL,
            description TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Seed parameter tables")
    parser.add_argument("--force", action="store_true", help="Re-seed even if data exists")
    parser.add_argument("--db", type=str, default=str(DB_PATH), help="Database path")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"Seeding parameters in {db_path}")
    print("=" * 60)

    conn = sqlite3.connect(str(db_path))

    try:
        # Ensure tables exist
        ensure_tables_exist(conn)

        # Seed each table
        total = 0
        total += seed_fx_rates(conn, args.force)
        total += seed_params(conn, args.force)
        total += seed_budget_caps(conn, args.force)

        conn.commit()

        print("=" * 60)
        print(f"Seeding complete. {total} rows modified.")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
