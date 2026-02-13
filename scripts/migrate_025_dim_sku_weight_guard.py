#!/usr/bin/env python3
"""
Add hard guard for dim_sku.weight_kg writes.

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

GUARD_KEY = "dim_sku_weight_kg"
GUARD_SOURCE = "sync_dim_sku_from_dim_sku_light"
TRIGGER_NAME = "trg_block_dim_sku_weight_update"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _trigger_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def validate_dim_sku_weight_guard_schema(db_path: Path) -> list[str]:
    errors: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "dim_sku"):
            errors.append("Missing table: dim_sku")
        if not _table_exists(conn, "dim_sku_weight_write_guard"):
            errors.append("Missing table: dim_sku_weight_write_guard")
        else:
            row = conn.execute(
                """
                SELECT allow_updates, source
                FROM dim_sku_weight_write_guard
                WHERE guard_key = ?
                """,
                (GUARD_KEY,),
            ).fetchone()
            if row is None:
                errors.append("Missing guard row: dim_sku_weight_kg")
        if not _trigger_exists(conn, TRIGGER_NAME):
            errors.append(f"Missing trigger: {TRIGGER_NAME}")
    finally:
        conn.close()
    return errors


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "dim_sku"):
            raise RuntimeError("dim_sku table is missing; run base schema migration first")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_sku_weight_write_guard (
                guard_key TEXT PRIMARY KEY,
                allow_updates INTEGER NOT NULL DEFAULT 0,
                source TEXT,
                expires_at TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO dim_sku_weight_write_guard
            (guard_key, allow_updates, source, expires_at, updated_at)
            VALUES (?, 0, NULL, NULL, datetime('now'))
            """,
            (GUARD_KEY,),
        )

        conn.execute(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME}")
        conn.execute(
            f"""
            CREATE TRIGGER {TRIGGER_NAME}
            BEFORE UPDATE OF weight_kg ON dim_sku
            FOR EACH ROW
            WHEN COALESCE(NEW.weight_kg, 0.0) <> COALESCE(OLD.weight_kg, 0.0)
             AND NOT EXISTS (
                SELECT 1
                FROM dim_sku_weight_write_guard
                WHERE guard_key = '{GUARD_KEY}'
                  AND allow_updates = 1
                  AND source = '{GUARD_SOURCE}'
                  AND datetime(COALESCE(expires_at, '1970-01-01')) > datetime('now')
             )
            BEGIN
                SELECT RAISE(ABORT, 'dim_sku.weight_kg updates are blocked; use sync_dim_sku_from_dim_sku_light');
            END
            """
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate dim_sku weight write guard")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.apply:
        errors = validate_dim_sku_weight_guard_schema(args.db)
        if errors:
            print("DRY RUN: dim_sku weight guard schema is not yet complete:")
            for err in errors:
                print(f"  - {err}")
            print("Use ENABLE_SCHEMA_WRITE=1 and --apply to run migration.")
            return 0
        print("DRY RUN: dim_sku weight guard schema already valid.")
        return 0

    if os.environ.get("ENABLE_SCHEMA_WRITE") != "1":
        print("ERROR: ENABLE_SCHEMA_WRITE=1 is required to apply migration.")
        return 1

    migrate(args.db)
    print("dim_sku weight guard migration applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
