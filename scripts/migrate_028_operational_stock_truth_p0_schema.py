#!/usr/bin/env python3
"""P0 schema for the operational stock truth rollout.

Default mode is validation/dry-run. Apply requires ENABLE_SCHEMA_WRITE=1 and
--apply. The migration is additive: it creates missing contract tables and adds
the stock ledger idempotency column/index used by downstream adjustment gates.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_operational_stock_schema import (
    DEFAULT_DB_PATH,
    validate_operational_stock_schema,
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if _table_exists(conn, table) and not _column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_manifest (
                source_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_path TEXT,
                source_sha256 TEXT,
                as_of_date TEXT,
                freshness_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                row_count INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pipeline_run (
                run_id TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                status TEXT NOT NULL,
                source_manifest_json TEXT NOT NULL DEFAULT '[]',
                validation_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                exception_count INTEGER NOT NULL DEFAULT 0,
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS validation_result (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                gate_name TEXT NOT NULL,
                status TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'INFO',
                message TEXT,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS exception_queue (
                exception_id TEXT PRIMARY KEY,
                run_id TEXT,
                domain TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS stock_anchor (
                anchor_id TEXT PRIMARY KEY,
                anchor_type TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                as_of_date TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                total_units INTEGER NOT NULL DEFAULT 0,
                approved_by TEXT,
                approved_at TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stock_adjustment_batch (
                batch_id TEXT PRIMARY KEY,
                anchor_id TEXT NOT NULL,
                method TEXT NOT NULL,
                method_version TEXT NOT NULL,
                reduction_rate REAL,
                target_units_delta INTEGER,
                generated_units_delta INTEGER,
                dry_run_report_path TEXT,
                approved_by TEXT,
                approved_at TEXT,
                applied_at TEXT,
                rollback_batch_id TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_time TEXT DEFAULT (datetime('now')),
                event_type TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                store_code TEXT DEFAULT 'UNIVERSAL',
                qty_change INTEGER NOT NULL,
                running_balance INTEGER,
                reference_id TEXT,
                reference_type TEXT,
                kaspi_offer_name TEXT,
                notes TEXT,
                input_source TEXT DEFAULT 'SYSTEM',
                created_by TEXT DEFAULT 'system',
                idempotency_key TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fact_inventory_snapshot_size (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                current_stock INTEGER NOT NULL DEFAULT 0,
                inbound_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(snapshot_date, sku_id)
            );

            CREATE TABLE IF NOT EXISTS offer_availability_snapshot (
                snapshot_id TEXT PRIMARY KEY,
                snapshot_date TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                offer_available_qty INTEGER,
                physical_stock_qty INTEGER,
                status TEXT NOT NULL DEFAULT 'UNKNOWN',
                source_manifest_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS order_status_event (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                order_id TEXT NOT NULL,
                stage_code TEXT NOT NULL,
                event_ts TEXT NOT NULL,
                source TEXT NOT NULL,
                raw_state TEXT,
                raw_status TEXT,
                source_status_change_at TEXT,
                source_run_id TEXT,
                flags_json TEXT NOT NULL DEFAULT '{}',
                source_row_hash TEXT,
                idempotency_key TEXT NOT NULL,
                observed_at TEXT DEFAULT (datetime('now')),
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fact_orders_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                channel_code TEXT DEFAULT 'KSP',
                kaspi_offer_name TEXT,
                kaspi_article TEXT,
                line_identity_key TEXT NOT NULL DEFAULT '',
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                quantity INTEGER DEFAULT 1,
                unit_price_kzt REAL,
                created_at TEXT,
                planned_shipment_date TEXT,
                actual_shipment_date TEXT,
                kaspi_status TEXT,
                kaspi_status_detail TEXT,
                internal_status TEXT DEFAULT 'NEW',
                status_updated_at TEXT,
                source TEXT DEFAULT 'EXCEL_EXPORT',
                source_file TEXT,
                imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, store_code, line_identity_key, sku_id)
            );

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
            );

            CREATE TABLE IF NOT EXISTS sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL DEFAULT '',
                store_code TEXT DEFAULT 'UNIVERSAL',
                quantity INTEGER NOT NULL,
                sell_price_kzt REAL,
                delivery_fee REAL,
                cogs REAL,
                net_rev REAL,
                profit REAL,
                status TEXT DEFAULT 'DELIVERED',
                return_flag INTEGER DEFAULT 0,
                return_date TEXT,
                ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source_file TEXT,
                api_updated_at TEXT,
                UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
            );

            CREATE TABLE IF NOT EXISTS return_qc_event (
                qc_event_id TEXT PRIMARY KEY,
                store_code TEXT NOT NULL,
                order_id TEXT NOT NULL,
                order_entry_id TEXT,
                sku_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                return_stage TEXT,
                qc_status TEXT NOT NULL,
                qc_ts TEXT,
                accepted_active_qty INTEGER NOT NULL DEFAULT 0,
                quarantine_qty INTEGER NOT NULL DEFAULT 0,
                rejected_qty INTEGER NOT NULL DEFAULT 0,
                writeoff_qty INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS po_header (
                po_id TEXT PRIMARY KEY,
                supplier_code TEXT DEFAULT 'SUPP_A',
                message_date TEXT,
                ship_date_seller TEXT,
                ship_date_cargo TEXT,
                alm_arrival_nom TEXT,
                ast_arrival_nom TEXT,
                status TEXT DEFAULT 'DRAFT',
                units_total INTEGER DEFAULT 0,
                units_received INTEGER DEFAULT 0,
                weight_nom_kg REAL DEFAULT 0,
                total_places INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS po_part (
                po_part_id TEXT PRIMARY KEY,
                po_id TEXT NOT NULL,
                supplier_id TEXT,
                message_date TEXT,
                cargo_send_date TEXT,
                estimated_arrival_date TEXT,
                actual_arrival_date TEXT,
                status TEXT,
                total_units INTEGER DEFAULT 0,
                base_cost_cny REAL DEFAULT 0,
                base_cost_kzt REAL,
                est_weight_kg REAL,
                actual_weight_kg REAL,
                total_bags INTEGER,
                cargo_freight_id TEXT,
                is_paid_base INTEGER,
                is_paid_dlv INTEGER,
                actual_dlv_pay_date TEXT,
                paid_dlv_usd REAL,
                paid_dlv_kzt REAL,
                final_usd_per_kg REAL,
                usd_kzt_rate REAL,
                actual_dlv_days INTEGER,
                to_pay_base_kzt REAL,
                to_pay_dlv_kzt REAL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS po_line (
                po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
                po_id TEXT NOT NULL,
                po_part_id TEXT,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                order_qty INTEGER NOT NULL,
                received_qty INTEGER DEFAULT 0,
                unit_cost_cny REAL,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fact_cashflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_ts TEXT,
                event_type TEXT NOT NULL,
                account TEXT NOT NULL,
                amount_kzt REAL NOT NULL,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                ref_type TEXT,
                ref_id TEXT,
                notes TEXT,
                source TEXT NOT NULL DEFAULT 'SYSTEM',
                run_id TEXT,
                event_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                cash_open REAL NOT NULL DEFAULT 0,
                cash_close REAL NOT NULL DEFAULT 0,
                receivables_open REAL NOT NULL DEFAULT 0,
                receivables_close REAL NOT NULL DEFAULT 0,
                inventory_cost_open REAL NOT NULL DEFAULT 0,
                inventory_cost_close REAL NOT NULL DEFAULT 0,
                capital_close REAL NOT NULL DEFAULT 0,
                cash_flow_kzt REAL NOT NULL DEFAULT 0,
                receivables_flow_kzt REAL NOT NULL DEFAULT 0,
                inventory_cost_flow_kzt REAL NOT NULL DEFAULT 0,
                inventory_on_hand_close REAL NOT NULL DEFAULT 0,
                inventory_inbound_close REAL NOT NULL DEFAULT 0,
                inventory_on_delivery_close REAL NOT NULL DEFAULT 0,
                run_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ads_source_refresh_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                merchant_id TEXT,
                store_code TEXT NOT NULL,
                date_start TEXT NOT NULL,
                date_end TEXT NOT NULL,
                product_rows_total INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                notes_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS ads_campaign_product_daily (
                date TEXT NOT NULL,
                store_code TEXT NOT NULL,
                campaign_id TEXT NOT NULL,
                campaign_name TEXT,
                sku_key TEXT NOT NULL DEFAULT '',
                cost_kzt REAL NOT NULL DEFAULT 0,
                impressions INTEGER,
                clicks INTEGER,
                source_run_id TEXT,
                coverage_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (date, store_code, campaign_id, sku_key)
            );

            CREATE TABLE IF NOT EXISTS owner_report_snapshot (
                snapshot_id TEXT PRIMARY KEY,
                run_id TEXT,
                report_date TEXT NOT NULL,
                trust_status TEXT NOT NULL,
                report_path TEXT,
                source_manifest_json TEXT NOT NULL DEFAULT '[]',
                exception_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )

        _ensure_column(conn, "stock_ledger", "idempotency_key", "TEXT")
        _ensure_column(conn, "fact_cashflow_daily", "cash_flow_kzt", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "fact_cashflow_daily", "receivables_flow_kzt", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "fact_cashflow_daily", "inventory_cost_flow_kzt", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "fact_cashflow_daily", "inventory_on_hand_close", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "fact_cashflow_daily", "inventory_inbound_close", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "fact_cashflow_daily", "inventory_on_delivery_close", "REAL NOT NULL DEFAULT 0")

        conn.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_ledger_idempotency_key
            ON stock_ledger(idempotency_key)
            WHERE idempotency_key IS NOT NULL;

            CREATE UNIQUE INDEX IF NOT EXISTS ux_order_status_event_idempotency
            ON order_status_event(idempotency_key);

            CREATE UNIQUE INDEX IF NOT EXISTS ux_return_qc_event_idempotency
            ON return_qc_event(idempotency_key);

            CREATE INDEX IF NOT EXISTS idx_stock_adjustment_batch_anchor
            ON stock_adjustment_batch(anchor_id);

            CREATE INDEX IF NOT EXISTS idx_stock_ledger_ref
            ON stock_ledger(reference_type, reference_id);

            CREATE INDEX IF NOT EXISTS idx_order_status_event_order
            ON order_status_event(store_code, order_id, event_ts);
            """
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate P0 operational stock truth schema")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_operational_stock_schema(args.db)
        if errors:
            print("DRY RUN: operational stock P0 schema migration required:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: operational stock P0 schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    errors = validate_operational_stock_schema(args.db)
    if errors:
        print("ERROR: operational stock P0 schema migration incomplete:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Operational stock P0 schema migrated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
