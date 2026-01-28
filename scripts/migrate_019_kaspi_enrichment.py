#!/usr/bin/env python3
"""
Migration 019: Kaspi order enrichment tables.

Adds:
- fact_order_entries_kaspi
- dim_point_of_service
- dim_masterproduct
- dim_merchantproduct
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
            CREATE TABLE IF NOT EXISTS fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                product_id TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                raw_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_order_entries_order ON fact_order_entries_kaspi(order_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_order_entries_store ON fact_order_entries_kaspi(store_code)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_point_of_service (
                pos_id TEXT PRIMARY KEY,
                store_code TEXT,
                raw_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_masterproduct (
                masterproduct_id TEXT PRIMARY KEY,
                raw_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_merchantproduct (
                merchantproduct_id TEXT PRIMARY KEY,
                masterproduct_id TEXT,
                raw_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration 019: Kaspi enrichment tables")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    migrate(args.db)
    print("Migration 019 applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
