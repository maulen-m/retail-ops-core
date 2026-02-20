#!/usr/bin/env python3
"""
Migration 018: Cashflow calendar tables.

Adds:
  - fact_cashflow_events (append-only spine)
  - fact_cashflow_daily (derived roll-forward)
  - fact_cashflow_commitments (optional)

Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
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
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_cashflow_events_hash ON fact_cashflow_events (event_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cashflow_events_date ON fact_cashflow_events (event_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cashflow_events_type ON fact_cashflow_events (event_type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cashflow_events_account ON fact_cashflow_events (account)"
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                cash_open REAL NOT NULL DEFAULT 0,
                cash_close REAL NOT NULL DEFAULT 0,
                receivables_open REAL NOT NULL DEFAULT 0,
                receivables_close REAL NOT NULL DEFAULT 0,
                inventory_cost_open REAL NOT NULL DEFAULT 0,
                inventory_cost_close REAL NOT NULL DEFAULT 0,
                capital_close REAL NOT NULL DEFAULT 0,
                sales_accrued_kzt REAL NOT NULL DEFAULT 0,
                payouts_received_kzt REAL NOT NULL DEFAULT 0,
                refunds_kzt REAL NOT NULL DEFAULT 0,
                po_payments_kzt REAL NOT NULL DEFAULT 0,
                expenses_kzt REAL NOT NULL DEFAULT 0,
                cogs_kzt REAL NOT NULL DEFAULT 0,
                cash_flow_kzt REAL NOT NULL DEFAULT 0,
                receivables_flow_kzt REAL NOT NULL DEFAULT 0,
                inventory_cost_flow_kzt REAL NOT NULL DEFAULT 0,
                profit_accrual_kzt REAL NOT NULL DEFAULT 0,
                run_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_cashflow_commitments (
                commit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                commit_date TEXT NOT NULL,
                commit_type TEXT NOT NULL,
                amount_kzt REAL NOT NULL,
                probability REAL,
                scenario_tag TEXT,
                ref_id TEXT,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cashflow_commitments_date ON fact_cashflow_commitments (commit_date)"
        )

        conn.commit()
        print("Migration complete: cashflow calendar tables ready.")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration 018: cashflow calendar tables")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    args = parser.parse_args()
    migrate(args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
