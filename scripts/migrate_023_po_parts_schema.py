#!/usr/bin/env python3
"""
Create/alter PO part schema for inbound split-shipment tracking.

Default: DRY RUN.
Apply requires ENABLE_SCHEMA_WRITE=1 and --apply.

Usage:
  python3 scripts/migrate_023_po_parts_schema.py
  ENABLE_SCHEMA_WRITE=1 python3 scripts/migrate_023_po_parts_schema.py --apply
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def validate_po_part_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "po_part"):
            errors.append("Missing table: po_part")
        else:
            required_cols = {
                "po_part_id",
                "po_id",
                "supplier_id",
                "message_date",
                "cargo_send_date",
                "estimated_arrival_date",
                "actual_arrival_date",
                "status",
                "total_units",
                "base_cost_cny",
                "updated_at",
            }
            cols = {row[1] for row in conn.execute("PRAGMA table_info(po_part)").fetchall()}
            missing = sorted(required_cols - cols)
            if missing:
                errors.append(f"po_part missing columns: {', '.join(missing)}")

        if not _table_exists(conn, "po_line"):
            errors.append("Missing table: po_line")
        elif not _column_exists(conn, "po_line", "po_part_id"):
            errors.append("Missing column: po_line.po_part_id")
    finally:
        conn.close()
    return errors


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS po_part (
                po_part_id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                supplier_id TEXT,
                message_date TEXT,
                cargo_send_date TEXT,
                estimated_arrival_date TEXT,
                actual_arrival_date TEXT,
                status TEXT,
                total_sku_keys INTEGER DEFAULT 0,
                total_units INTEGER DEFAULT 0,
                base_cost_cny REAL DEFAULT 0,
                base_cost_kzt REAL,
                est_weight_kg REAL,
                est_delivery_usd REAL,
                total_bags INTEGER,
                qty_delta INTEGER,
                est_delivery_kzt REAL,
                is_paid_base INTEGER,
                is_paid_dlv INTEGER,
                to_pay_base_kzt REAL,
                to_pay_dlv_kzt REAL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_po_part_po_id ON po_part(po_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_po_part_status ON po_part(status)"
        )

        if not _table_exists(conn, "po_line"):
            raise RuntimeError("Missing po_line table; run ledger migration before migrate_023")

        if not _column_exists(conn, "po_line", "po_part_id"):
            conn.execute("ALTER TABLE po_line ADD COLUMN po_part_id TEXT")

        if not _index_exists(conn, "idx_po_line_part"):
            conn.execute("CREATE INDEX idx_po_line_part ON po_line(po_part_id)")
        if not _index_exists(conn, "ux_po_line_po_part_sku_size"):
            conn.execute(
                "CREATE UNIQUE INDEX ux_po_line_po_part_sku_size "
                "ON po_line(po_id, po_part_id, sku_key, my_size)"
            )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate PO part schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply migration")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_po_part_schema(args.db)
        if errors:
            print("DRY RUN: PO part schema is not yet complete:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: PO part schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    print("PO part schema migrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
