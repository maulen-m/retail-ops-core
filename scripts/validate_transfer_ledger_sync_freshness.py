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
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"
CONFIG_PATH = PROJECT_ROOT / "config" / "transfer_ledger_sync.yaml"


def _load_config() -> tuple[list[str], int, dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return [], 25, {}
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    settings = data.get("settings") or {}
    required = settings.get("required_sources") or []
    max_age = int(settings.get("max_age_hours") or 25)
    fallback = settings.get("manual_cash_snapshot_fallback") or {}
    return list(required), max_age, dict(fallback) if isinstance(fallback, dict) else {}


def _parse_as_of(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S GMT+5", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _manual_cash_snapshot_is_fresh(
    *,
    source: str,
    fallback: dict[str, Any],
    max_age: int,
    now: datetime,
) -> tuple[bool, str]:
    if not fallback.get("enabled"):
        return False, "manual cash snapshot fallback disabled"
    accepted_sources = set(fallback.get("accepted_for_sources") or [])
    if accepted_sources and source not in accepted_sources:
        return False, f"{source} not accepted for manual cash snapshot fallback"

    snapshot_path = PROJECT_ROOT / str(fallback.get("snapshot_path") or "config/bank_accounts.yaml")
    history_path = PROJECT_ROOT / str(fallback.get("history_path") or "config/bank_accounts_history.yaml")
    source_contains = str(fallback.get("source_contains") or "").strip()
    if not snapshot_path.exists():
        return False, f"manual cash snapshot missing: {snapshot_path}"
    if not history_path.exists():
        return False, f"manual cash history missing: {history_path}"

    snapshot_data = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
    as_of_raw = snapshot_data.get("as_of")
    as_of = _parse_as_of(as_of_raw)
    if as_of is None:
        return False, f"manual cash snapshot has invalid as_of={as_of_raw!r}"
    age_hours = (now - as_of).total_seconds() / 3600
    if age_hours > max_age:
        return False, f"manual cash snapshot stale ({age_hours:.1f}h ago)"

    history_data = yaml.safe_load(history_path.read_text(encoding="utf-8")) or {}
    entries = history_data.get("entries") or []
    if not isinstance(entries, list):
        return False, f"manual cash history invalid: {history_path}"
    matched_entry = None
    for entry in entries:
        if str(entry.get("as_of") or "").strip() == str(as_of_raw).strip():
            matched_entry = entry
            break
    if not matched_entry:
        return False, f"manual cash history missing matching as_of={as_of_raw}"
    history_source = str(matched_entry.get("source") or "")
    if source_contains and source_contains not in history_source:
        return False, f"manual cash history source {history_source!r} does not contain {source_contains!r}"

    return True, f"manual Cash_Balances snapshot age {age_hours:.1f}h ({as_of_raw})"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def validate(db_path: Path) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    sources, max_age, manual_cash_fallback = _load_config()
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
                fallback_ok, fallback_reason = _manual_cash_snapshot_is_fresh(
                    source=source,
                    fallback=manual_cash_fallback,
                    max_age=max_age,
                    now=now,
                )
                if fallback_ok:
                    print(f"WARN: {source} missing last_success_ts; accepted via {fallback_reason}")
                else:
                    print(f"FAIL: {source} missing last_success_ts ({fallback_reason})")
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
                fallback_ok, fallback_reason = _manual_cash_snapshot_is_fresh(
                    source=source,
                    fallback=manual_cash_fallback,
                    max_age=max_age,
                    now=now,
                )
                if fallback_ok:
                    print(
                        f"WARN: {source} sync stale ({age_hours:.1f}h ago); "
                        f"accepted via {fallback_reason}"
                    )
                else:
                    print(f"FAIL: {source} sync stale ({age_hours:.1f}h ago; {fallback_reason})")
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
