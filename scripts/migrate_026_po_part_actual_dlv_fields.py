#!/usr/bin/env python3
"""
Add actual DLV tracking fields to po_part for workbook parity.

Default: dry-run.
Apply requires ENABLE_SCHEMA_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"

REQUIRED_COLUMNS: dict[str, str] = {
    "cargo_freight_id": "TEXT",
    "actual_dlv_pay_date": "TEXT",
    "actual_weight_kg": "REAL",
    "paid_dlv_usd": "REAL",
    "paid_dlv_kzt": "REAL",
    "final_usd_per_kg": "REAL",
    "usd_kzt_rate": "REAL",
    "actual_dlv_days": "INTEGER",
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def validate_po_part_actual_fields_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "po_part"):
            errors.append("Missing table: po_part")
            return errors
        cols = _table_columns(conn, "po_part")
        missing = sorted(col for col in REQUIRED_COLUMNS if col not in cols)
        if missing:
            errors.append(f"po_part missing columns: {', '.join(missing)}")
    finally:
        conn.close()
    return errors


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "po_part"):
            raise RuntimeError("Missing table: po_part")
        cols = _table_columns(conn, "po_part")
        for col, ddl_type in REQUIRED_COLUMNS.items():
            if col in cols:
                continue
            conn.execute(f"ALTER TABLE po_part ADD COLUMN {col} {ddl_type}")
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate po_part actual DLV fields")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_po_part_actual_fields_schema(args.db)
        if errors:
            print("DRY RUN: po_part actual DLV fields migration required:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: po_part actual DLV fields schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    print("po_part actual DLV fields migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
