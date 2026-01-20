#!/usr/bin/env python3
"""
Migration 016: allow multiple demand override windows per SKU.

Replaces dim_demand_overrides (sku_key PRIMARY KEY) with:
  id INTEGER PRIMARY KEY,
  sku_key TEXT,
  d_override REAL,
  start_date, end_date, reason, source, active_flag, created_at, updated_at

Creates unique index on (sku_key, start_date, end_date).
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_demand_overrides'"
        )
        if cursor.fetchone() is None:
            print("dim_demand_overrides does not exist; nothing to migrate.")
            return

        cursor.execute("PRAGMA table_info(dim_demand_overrides)")
        cols = {row[1] for row in cursor.fetchall()}
        if "id" in cols:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_demand_overrides_window "
                "ON dim_demand_overrides(sku_key, start_date, end_date)"
            )
            conn.commit()
            print("dim_demand_overrides already supports multi-window overrides.")
            return

        cursor.execute("""
            CREATE TABLE dim_demand_overrides_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku_key TEXT NOT NULL,
                d_override REAL NOT NULL,
                start_date TEXT,
                end_date TEXT,
                reason TEXT,
                source TEXT,
                active_flag INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            INSERT INTO dim_demand_overrides_v2
            (sku_key, d_override, start_date, end_date, reason, source, active_flag, created_at, updated_at)
            SELECT sku_key, d_override, start_date, end_date, reason, source, active_flag, created_at, updated_at
            FROM dim_demand_overrides
        """)
        cursor.execute("DROP TABLE dim_demand_overrides")
        cursor.execute("ALTER TABLE dim_demand_overrides_v2 RENAME TO dim_demand_overrides")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_demand_overrides_window "
            "ON dim_demand_overrides(sku_key, start_date, end_date)"
        )
        conn.commit()
        print("Migration complete: dim_demand_overrides now supports multiple windows.")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate demand overrides to multi-window schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: Database not found: {args.db}")
        return 1

    migrate(args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
