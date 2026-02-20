#!/usr/bin/env python3
"""
Add `synced_at` to fact_orders_kaspi for chronology-safe sync bookkeeping.

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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def validate_synced_at_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "fact_orders_kaspi"):
            errors.append("Missing table: fact_orders_kaspi")
        elif not _column_exists(conn, "fact_orders_kaspi", "synced_at"):
            errors.append("Missing column: fact_orders_kaspi.synced_at")
    finally:
        conn.close()
    return errors


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi table is missing; run base schema migration first")
        if not _column_exists(conn, "fact_orders_kaspi", "synced_at"):
            columns = _table_columns(conn, "fact_orders_kaspi")
            conn.execute("ALTER TABLE fact_orders_kaspi ADD COLUMN synced_at TEXT DEFAULT CURRENT_TIMESTAMP")
            coalesce_parts: list[str] = []
            if "status_updated_at" in columns:
                coalesce_parts.append("status_updated_at")
            if "updated_at" in columns:
                coalesce_parts.append("updated_at")
            coalesce_parts.append("CURRENT_TIMESTAMP")
            coalesce_expr = ", ".join(coalesce_parts)
            conn.execute(
                f"""
                UPDATE fact_orders_kaspi
                SET synced_at = COALESCE({coalesce_expr})
                WHERE synced_at IS NULL
                """
            )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate fact_orders_kaspi synced_at column")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_synced_at_schema(args.db)
        if errors:
            print("DRY RUN: synced_at migration required:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: synced_at schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    print("synced_at migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
