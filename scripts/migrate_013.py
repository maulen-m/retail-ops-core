#!/usr/bin/env python3
"""
Migration 013: Extend dim_sku columns for truth workbook sync.

Adds:
- cogs_kzt
- avg_sell_price_kzt_used
- avg_sell_price_source
- price_missing_flag
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"

REQUIRED_COLUMNS = {
    "cogs_kzt": "REAL",
    "avg_sell_price_kzt_used": "REAL",
    "avg_sell_price_source": "TEXT",
    "price_missing_flag": "INTEGER",
}


def migrate(db_path: Path | None = None) -> None:
    db_path = db_path or DB_PATH
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_sku'"
    )
    if not cursor.fetchone():
        conn.close()
        return

    cursor.execute("PRAGMA table_info(dim_sku)")
    existing = {row[1] for row in cursor.fetchall()}

    for col, col_type in REQUIRED_COLUMNS.items():
        if col in existing:
            continue
        try:
            cursor.execute(f"ALTER TABLE dim_sku ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                continue
            raise

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
