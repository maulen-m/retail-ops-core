#!/usr/bin/env python3
"""Create fact_order_status_observations for WebUI/API audit history."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"


REQUIRED_COLUMNS = {
    "id",
    "order_id",
    "store_code",
    "status_internal",
    "observed_at",
    "source",
    "ledger_run_id",
    "source_detail",
    "created_at",
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


def validate_order_status_observation_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "fact_order_status_observations"):
            errors.append("Missing table: fact_order_status_observations")
        else:
            missing = sorted(REQUIRED_COLUMNS - _table_columns(conn, "fact_order_status_observations"))
            if missing:
                errors.append(
                    "Missing columns: " + ", ".join(f"fact_order_status_observations.{col}" for col in missing)
                )
    finally:
        conn.close()
    return errors


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fact_order_status_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                status_internal TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                source TEXT NOT NULL,
                ledger_run_id TEXT,
                source_detail TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, store_code, status_internal, observed_at, source)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_order_status_observations_lookup
            ON fact_order_status_observations(store_code, order_id, observed_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_order_status_observations_source
            ON fact_order_status_observations(source, observed_at)
            """
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate order status observations table")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_order_status_observation_schema(args.db)
        if errors:
            print("DRY RUN: order status observations migration required:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: order status observation schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    print("order status observations migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
