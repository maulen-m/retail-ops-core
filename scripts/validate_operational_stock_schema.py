#!/usr/bin/env python3
"""Validate the P0 operational stock truth schema contract."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"

REQUIRED_OPERATIONAL_TABLES: dict[str, set[str]] = {
    "source_manifest": {
        "source_id",
        "source_type",
        "source_path",
        "source_sha256",
        "as_of_date",
        "freshness_status",
        "created_at",
    },
    "pipeline_run": {
        "run_id",
        "run_type",
        "as_of_date",
        "status",
        "source_manifest_json",
        "validation_status",
        "exception_count",
        "started_at",
        "finished_at",
    },
    "validation_result": {
        "result_id",
        "run_id",
        "gate_name",
        "status",
        "severity",
        "message",
        "created_at",
    },
    "exception_queue": {
        "exception_id",
        "run_id",
        "domain",
        "severity",
        "status",
        "reason",
        "created_at",
    },
    "stock_anchor": {
        "anchor_id",
        "anchor_type",
        "source_path",
        "source_sha256",
        "snapshot_date",
        "as_of_date",
        "row_count",
        "total_units",
        "status",
        "created_at",
    },
    "stock_adjustment_batch": {
        "batch_id",
        "anchor_id",
        "method",
        "method_version",
        "reduction_rate",
        "status",
        "dry_run_report_path",
        "created_at",
        "applied_at",
        "rollback_batch_id",
    },
    "stock_ledger": {
        "ledger_id",
        "event_date",
        "event_type",
        "sku_key",
        "sku_id",
        "my_size",
        "store_code",
        "qty_change",
        "reference_id",
        "reference_type",
        "idempotency_key",
    },
    "fact_inventory_snapshot_size": {
        "snapshot_date",
        "sku_id",
        "sku_key",
        "my_size",
        "current_stock",
        "inbound_stock",
    },
    "offer_availability_snapshot": {
        "snapshot_id",
        "snapshot_date",
        "store_code",
        "sku_key",
        "sku_id",
        "my_size",
        "offer_available_qty",
        "physical_stock_qty",
        "status",
    },
    "order_status_event": {
        "event_id",
        "store_code",
        "order_id",
        "stage_code",
        "event_ts",
        "source",
        "idempotency_key",
        "created_at",
    },
    "fact_orders_kaspi": {
        "order_id",
        "store_code",
        "internal_status",
        "status_updated_at",
        "source",
        "updated_at",
    },
    "fact_order_entries_kaspi": {
        "entry_id",
        "order_id",
        "store_code",
        "offer_id",
        "quantity",
        "unit_price_kzt",
        "updated_at",
    },
    "sales_fact_v2": {
        "order_id",
        "order_date",
        "sku_key",
        "sku_id",
        "my_size",
        "quantity",
        "status",
    },
    "return_qc_event": {
        "qc_event_id",
        "store_code",
        "order_id",
        "sku_id",
        "quantity",
        "qc_status",
        "accepted_active_qty",
        "quarantine_qty",
        "idempotency_key",
    },
    "po_header": {
        "po_id",
        "supplier_code",
        "status",
        "units_total",
        "units_received",
    },
    "po_part": {
        "po_part_id",
        "po_id",
        "status",
        "total_units",
        "is_paid_base",
        "is_paid_dlv",
    },
    "po_line": {
        "po_line_id",
        "po_id",
        "po_part_id",
        "sku_key",
        "sku_id",
        "my_size",
        "order_qty",
        "received_qty",
    },
    "fact_cashflow_events": {
        "event_date",
        "event_type",
        "account",
        "amount_kzt",
        "event_hash",
    },
    "fact_cashflow_daily": {
        "date",
        "cash_open",
        "cash_close",
        "cash_flow_kzt",
        "receivables_open",
        "receivables_close",
        "receivables_flow_kzt",
        "inventory_cost_open",
        "inventory_cost_close",
        "inventory_cost_flow_kzt",
    },
    "ads_source_refresh_runs": {
        "run_id",
        "store_code",
        "date_start",
        "date_end",
        "status",
        "started_at",
        "finished_at",
    },
    "ads_campaign_product_daily": {
        "date",
        "store_code",
        "campaign_id",
        "sku_key",
        "cost_kzt",
        "source_run_id",
        "coverage_status",
    },
    "owner_report_snapshot": {
        "snapshot_id",
        "run_id",
        "report_date",
        "trust_status",
        "report_path",
        "created_at",
    },
}

REQUIRED_INDEXES = {
    "ux_stock_ledger_idempotency_key",
    "ux_order_status_event_idempotency",
    "ux_return_qc_event_idempotency",
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    return row is not None


def validate_operational_stock_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        for table, required_columns in REQUIRED_OPERATIONAL_TABLES.items():
            if not _table_exists(conn, table):
                errors.append(f"Missing table: {table}")
                continue
            columns = _table_columns(conn, table)
            missing = sorted(required_columns - columns)
            if missing:
                errors.append(f"{table} missing columns: {', '.join(missing)}")

        for index_name in sorted(REQUIRED_INDEXES):
            if not _index_exists(conn, index_name):
                errors.append(f"Missing index: {index_name}")
    finally:
        conn.close()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate P0 operational stock truth schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        errors = [f"Database not found: {args.db}"]
    else:
        errors = validate_operational_stock_schema(args.db)

    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("OPERATIONAL STOCK SCHEMA FAILURES:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("OK: operational stock schema valid")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
