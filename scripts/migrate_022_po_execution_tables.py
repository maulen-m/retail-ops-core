#!/usr/bin/env python3
"""
Create/alter PO execution tables to canonical schema.

Default: DRY RUN. Apply requires ENABLE_SCHEMA_WRITE=1 and --apply.

Usage:
  python scripts/migrate_022_po_execution_tables.py
  ENABLE_SCHEMA_WRITE=1 python scripts/migrate_022_po_execution_tables.py --apply
  ENABLE_SCHEMA_WRITE=1 python scripts/migrate_022_po_execution_tables.py --apply --db /path/to/app.db
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _add_column(conn, table: str, column_def: str, column_name: str) -> None:
    if not _column_exists(conn, table, column_name):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def migrate(db_path: Path) -> None:
    with get_db(db_path) as conn:
        if not _table_exists(conn, "fact_po_draft"):
            conn.execute(
                """
                CREATE TABLE fact_po_draft (
                    draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT DEFAULT (datetime('now')),
                    status TEXT DEFAULT 'PENDING',
                    supplier_code TEXT DEFAULT 'DEFAULT',
                    total_units INTEGER NOT NULL,
                    total_cost_cny REAL NOT NULL,
                    total_cost_kzt REAL NOT NULL,
                    total_po_value_kzt REAL NOT NULL DEFAULT 0,
                    total_order_qty INTEGER NOT NULL DEFAULT 0,
                    skus_count INTEGER NOT NULL DEFAULT 0,
                    roic_action_summary TEXT,
                    guardrail_status TEXT,
                    approved_at TEXT,
                    approved_by TEXT,
                    rejection_reason TEXT,
                    expires_at TEXT,
                    generation_reason TEXT,
                    confidence_score REAL,
                    notes TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
        else:
            _add_column(conn, "fact_po_draft", "total_po_value_kzt REAL NOT NULL DEFAULT 0", "total_po_value_kzt")
            _add_column(conn, "fact_po_draft", "total_order_qty INTEGER NOT NULL DEFAULT 0", "total_order_qty")
            _add_column(conn, "fact_po_draft", "skus_count INTEGER NOT NULL DEFAULT 0", "skus_count")
            _add_column(conn, "fact_po_draft", "roic_action_summary TEXT", "roic_action_summary")
            _add_column(conn, "fact_po_draft", "guardrail_status TEXT", "guardrail_status")
            _add_column(conn, "fact_po_draft", "updated_at TEXT DEFAULT (datetime('now'))", "updated_at")

        if not _table_exists(conn, "fact_po_draft_lines"):
            conn.execute(
                """
                CREATE TABLE fact_po_draft_lines (
                    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL REFERENCES fact_po_draft(draft_id),
                    sku_key TEXT NOT NULL,
                    sku_id TEXT NOT NULL,
                    my_size TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_cost_cny REAL NOT NULL,
                    current_stock INTEGER,
                    rop INTEGER,
                    d_forecast REAL,
                    roic_pct REAL,
                    UNIQUE(draft_id, sku_id)
                )
                """
            )

        if not _table_exists(conn, "fact_po_approvals"):
            conn.execute(
                """
                CREATE TABLE fact_po_approvals (
                    approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER NOT NULL REFERENCES fact_po_draft(draft_id),
                    sku_key TEXT DEFAULT 'ALL',
                    roic_action TEXT,
                    approved_by TEXT,
                    approved_at TEXT DEFAULT (datetime('now')),
                    decision TEXT NOT NULL,
                    notes TEXT,
                    po_value_kzt REAL,
                    order_qty INTEGER
                )
                """
            )

        if not _table_exists(conn, "fact_po_execution"):
            conn.execute(
                """
                CREATE TABLE fact_po_execution (
                    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    draft_id INTEGER REFERENCES fact_po_draft(draft_id),
                    po_id TEXT REFERENCES fact_po_lines(po_id),
                    approval_id INTEGER,
                    executed_lines INTEGER DEFAULT 0,
                    total_value_kzt REAL DEFAULT 0,
                    notes TEXT,
                    executed_by TEXT DEFAULT 'SYSTEM',
                    executed_at TEXT DEFAULT (datetime('now')),
                    planned_units INTEGER NOT NULL DEFAULT 0,
                    received_units INTEGER,
                    planned_arrival_date TEXT,
                    actual_arrival_date TEXT,
                    defect_units INTEGER DEFAULT 0,
                    defect_rate REAL,
                    planned_cost_cny REAL,
                    actual_cost_cny REAL,
                    cost_variance_pct REAL,
                    status TEXT DEFAULT 'IN_TRANSIT',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
        else:
            _add_column(conn, "fact_po_execution", "approval_id INTEGER", "approval_id")
            _add_column(conn, "fact_po_execution", "planned_units INTEGER NOT NULL DEFAULT 0", "planned_units")
            _add_column(conn, "fact_po_execution", "executed_lines INTEGER DEFAULT 0", "executed_lines")
            _add_column(conn, "fact_po_execution", "total_value_kzt REAL DEFAULT 0", "total_value_kzt")
            _add_column(conn, "fact_po_execution", "notes TEXT", "notes")
            _add_column(conn, "fact_po_execution", "executed_by TEXT DEFAULT 'SYSTEM'", "executed_by")
            _add_column(conn, "fact_po_execution", "executed_at TEXT DEFAULT (datetime('now'))", "executed_at")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate PO execution tables")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DB path (default: db/app.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply migration (default: dry-run)",
    )
    args = parser.parse_args()

    if not args.apply:
        print("DRY RUN: no changes applied. Use ENABLE_SCHEMA_WRITE=1 and --apply to run.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    print("PO execution tables migrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
