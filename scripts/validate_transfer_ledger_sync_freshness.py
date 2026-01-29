#!/usr/bin/env python3
"""
Validate transfer-ledger import sync freshness for Gmail/Binance sources.
Fails if any required source has no recent successful sync.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"
CONFIG_PATH = PROJECT_ROOT / "config" / "transfer_ledger_sync.yaml"


def _load_config() -> tuple[list[str], int]:
    if not CONFIG_PATH.exists():
        return [], 25
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    settings = data.get("settings") or {}
    required = settings.get("required_sources") or []
    max_age = int(settings.get("max_age_hours") or 25)
    return list(required), max_age


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def validate(db_path: Path) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    sources, max_age = _load_config()
    if not sources:
        print("WARN: No transfer_ledger sync sources configured.")
        return 0

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "transfer_ledger_sync_log"):
            print("FAIL: transfer_ledger_sync_log missing (no sync history)")
            return 1

        now = datetime.now()
        cutoff = now - timedelta(hours=max_age)
        failures = 0
        for source in sources:
            row = conn.execute(
                "SELECT last_success_ts FROM transfer_ledger_sync_log WHERE source = ?",
                (source,),
            ).fetchone()
            if not row or not row["last_success_ts"]:
                print(f"FAIL: {source} missing last_success_ts")
                failures += 1
                continue
            try:
                last_ts = datetime.fromisoformat(row["last_success_ts"])
            except Exception:
                print(f"FAIL: {source} has invalid last_success_ts={row['last_success_ts']}")
                failures += 1
                continue
            if last_ts < cutoff:
                age_hours = (now - last_ts).total_seconds() / 3600
                print(f"FAIL: {source} sync stale ({age_hours:.1f}h ago)")
                failures += 1
            else:
                age_hours = (now - last_ts).total_seconds() / 3600
                print(f"OK: {source} sync age {age_hours:.1f}h")

        if failures:
            print(f"FAIL: {failures} source(s) stale")
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate transfer-ledger sync freshness")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    return validate(args.db)


if __name__ == "__main__":
    raise SystemExit(main())
