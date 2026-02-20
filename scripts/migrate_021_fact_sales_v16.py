#!/usr/bin/env python3
"""
Migration 021: fact_sales_v16 (API order-entry sales).
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_sales_v16 (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                offer_id TEXT,
                sku_key TEXT,
                sku_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                delivery_fee_kzt REAL,
                net_rev_kzt REAL,
                source TEXT,
                run_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration 021: fact_sales_v16")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    migrate(args.db)
    print("Migration 021 applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
