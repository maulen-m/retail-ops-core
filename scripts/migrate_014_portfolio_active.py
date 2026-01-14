#!/usr/bin/env python3
"""
Create portfolio_active table for explicit portfolio scoping.

Usage:
  python scripts/migrate_014_portfolio_active.py
  python scripts/migrate_014_portfolio_active.py --seed-from-dim-sku
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.db import get_db, DEFAULT_DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Create portfolio_active table")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DB path (default: db/app.db)",
    )
    parser.add_argument(
        "--seed-from-dim-sku",
        action="store_true",
        help="Seed portfolio_active from dim_sku.active_flag",
    )
    args = parser.parse_args()

    with get_db(args.db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_active (
                sku_key TEXT PRIMARY KEY,
                active_flag INTEGER DEFAULT 1,
                notes TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_portfolio_active_flag ON portfolio_active(active_flag)"
        )

        if args.seed_from_dim_sku:
            conn.execute(
                """
                INSERT OR IGNORE INTO portfolio_active (sku_key, active_flag)
                SELECT sku_key, active_flag
                FROM dim_sku
                WHERE active_flag = 1
                """
            )

    print("portfolio_active table ready.")
    if args.seed_from_dim_sku:
        print("Seeded from dim_sku.active_flag")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
