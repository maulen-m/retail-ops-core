#!/usr/bin/env python3
"""
Validate Kaspi Orders API sync freshness.

Fails if any sync-enabled store has not synced within max-age hours.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"
CONFIG_PATH = PROJECT_ROOT / "config" / "kaspi_stores.yaml"


def _load_store_codes() -> list[str]:
    if not CONFIG_PATH.exists():
        return []
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    stores = []
    for code, meta in (data.get("stores") or {}).items():
        if meta.get("sync_enabled", True):
            stores.append(code)
    return stores


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def validate(db_path: Path, max_age_hours: int) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "kaspi_order_sync_log"):
            print("FAIL: kaspi_order_sync_log missing (no sync history)")
            return 1

        now = datetime.now()
        cutoff = now - timedelta(hours=max_age_hours)

        stores = _load_store_codes()
        if not stores:
            print("WARN: No stores configured for sync check.")
            return 0

        failures = 0
        for store in stores:
            row = conn.execute(
                "SELECT last_success_ts FROM kaspi_order_sync_log WHERE store_code = ?",
                (store,),
            ).fetchone()
            if not row or not row["last_success_ts"]:
                print(f"FAIL: {store} missing sync log")
                failures += 1
                continue
            try:
                last_ts = datetime.fromisoformat(row["last_success_ts"])
            except Exception:
                print(f"FAIL: {store} has invalid last_success_ts={row['last_success_ts']}")
                failures += 1
                continue
            if last_ts < cutoff:
                age_hours = (now - last_ts).total_seconds() / 3600
                print(f"FAIL: {store} sync stale ({age_hours:.1f}h ago)")
                failures += 1
            else:
                age_hours = (now - last_ts).total_seconds() / 3600
                print(f"OK: {store} sync age {age_hours:.1f}h")

        if failures:
            print(f"FAIL: {failures} store(s) stale")
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Kaspi order sync freshness")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--max-age-hours", type=int, default=25)
    args = parser.parse_args()
    return validate(args.db, args.max_age_hours)


if __name__ == "__main__":
    raise SystemExit(main())
