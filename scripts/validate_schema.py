#!/usr/bin/env python3
"""
Read-only schema validation for PO execution tables.

Usage:
  python scripts/validate_schema.py [--db path]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"

REQUIRED_TABLES: dict[str, set[str]] = {
    "fact_po_draft": {
        "draft_id",
        "status",
        "supplier_code",
        "total_units",
        "total_cost_cny",
        "total_cost_kzt",
        "total_po_value_kzt",
        "total_order_qty",
        "skus_count",
        "roic_action_summary",
        "guardrail_status",
        "notes",
        "created_at",
        "updated_at",
    },
    "fact_po_draft_lines": {
        "line_id",
        "draft_id",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "unit_cost_cny",
        "roic_pct",
    },
    "fact_po_approvals": {
        "approval_id",
        "draft_id",
        "sku_key",
        "roic_action",
        "approved_by",
        "approved_at",
        "decision",
        "notes",
        "po_value_kzt",
        "order_qty",
    },
    "fact_po_execution": {
        "execution_id",
        "draft_id",
        "po_id",
        "approval_id",
        "planned_units",
        "executed_lines",
        "total_value_kzt",
        "notes",
        "executed_by",
        "executed_at",
        "status",
    },
}

OPTIONAL_TABLES: dict[str, set[str]] = {
    "po_header": {
        "po_id",
        "supplier_code",
        "status",
        "message_date",
        "ship_date_seller",
        "ship_date_cargo",
        "alm_arrival_nom",
        "ast_arrival_nom",
        "units_total",
        "units_received",
        "weight_nom_kg",
        "total_places",
    },
    "po_part": {
        "po_part_id",
        "po_id",
        "status",
        "est_weight_kg",
        "actual_weight_kg",
        "total_bags",
        "cargo_freight_id",
        "total_units",
        "is_paid_base",
        "is_paid_dlv",
        "actual_dlv_pay_date",
        "paid_dlv_usd",
        "paid_dlv_kzt",
        "final_usd_per_kg",
        "usd_kzt_rate",
        "actual_dlv_days",
        "to_pay_base_kzt",
        "to_pay_dlv_kzt",
    },
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def validate_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        for table, required_cols in REQUIRED_TABLES.items():
            if not _table_exists(conn, table):
                errors.append(f"Missing table: {table}")
                continue
            cols = _table_columns(conn, table)
            missing = sorted(col for col in required_cols if col not in cols)
            if missing:
                errors.append(f"{table} missing columns: {', '.join(missing)}")
        for table, required_cols in OPTIONAL_TABLES.items():
            if not _table_exists(conn, table):
                continue
            cols = _table_columns(conn, table)
            missing = sorted(col for col in required_cols if col not in cols)
            if missing:
                errors.append(f"{table} missing columns: {', '.join(missing)}")
    finally:
        conn.close()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PO execution schema")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="DB path (default: db/app.db)",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    if not args.db.exists():
        if args.json:
            print(json.dumps({"ok": False, "errors": [f"Database not found: {args.db}"]}, ensure_ascii=False))
        else:
            print(f"ERROR: Database not found: {args.db}")
        return 1

    errors = validate_schema(args.db)
    if errors:
        if args.json:
            print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        else:
            print("SCHEMA FAILURES:")
            for err in errors:
                print(f"  - {err}")
        return 1

    if args.json:
        print(json.dumps({"ok": True, "errors": []}, ensure_ascii=False))
    else:
        print("OK: PO execution schema valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
