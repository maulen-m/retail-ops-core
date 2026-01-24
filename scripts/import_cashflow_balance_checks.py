#!/usr/bin/env python3
"""
Import manual balance check events from config/bank_accounts.yaml.

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
import sys
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.business_params import get_fx_rates

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "bank_accounts.yaml"
EXPORT_PATH = PROJECT_ROOT / "exports" / "balance_check_import_report.txt"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _event_hash(event: dict) -> str:
    parts = [
        str(event.get("event_date") or ""),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.4f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def import_balance_checks(config_path: Path, db_path: Path, apply: bool, run_id: str) -> int:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    as_of = config.get("as_of")
    if not as_of:
        raise ValueError("bank_accounts.yaml missing 'as_of'")

    fx_rates = get_fx_rates(date.fromisoformat(as_of), db_path=db_path)
    report_lines = [f"as_of: {as_of}", f"usd_kzt: {fx_rates.usd_kzt}"]

    events = []
    total_kzt = 0.0
    skipped = 0

    stores = config.get("stores", {})
    for store_code, store_meta in stores.items():
        accounts = (store_meta or {}).get("accounts", {})
        for account_name, data in accounts.items():
            amount_kzt = data.get("balance_kzt")
            notes = []
            if amount_kzt is None:
                if data.get("balance_usd") is not None:
                    amount_kzt = float(data.get("balance_usd")) * fx_rates.usd_kzt
                    notes.append("USD→KZT")
                elif data.get("balance_usdt") is not None:
                    amount_kzt = float(data.get("balance_usdt")) * fx_rates.usd_kzt
                    notes.append("USDT→KZT")
                elif data.get("balance_rub") is not None:
                    amount_kzt = 0.0
                    notes.append("RUB balance tracked separately (no FX rate)")
                else:
                    skipped += 1
                    continue
            amount_kzt = float(amount_kzt)
            if abs(amount_kzt) < 0.005:
                skipped += 1
                continue

            total_kzt += amount_kzt
            events.append(
                {
                    "event_date": as_of,
                    "event_type": "BALANCE_CHECK",
                    "account": "CASH",
                    "amount_kzt": round(amount_kzt, 2),
                    "store_code": store_code,
                    "ref_type": "BALANCE_CHECK",
                    "ref_id": f"{store_code}:{account_name}",
                    "notes": "; ".join(notes) if notes else None,
                    "source": "MANUAL",
                    "run_id": run_id,
                }
            )

    report_lines.append(f"accounts_imported: {len(events)}")
    report_lines.append(f"accounts_skipped: {skipped}")
    report_lines.append(f"total_balance_kzt: {round(total_kzt, 2)}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        for event in events:
            event["event_hash"] = _event_hash(event)

        existing_hashes = set()
        if events:
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(
                        ",".join("?" * len(events))
                    ),
                    [e["event_hash"] for e in events],
                ).fetchall()
            }

        new_events = [e for e in events if e["event_hash"] not in existing_hashes]
        report_lines.append(f"new_events: {len(new_events)}")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for event in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, store_code, ref_type, ref_id,
                        notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["event_date"],
                        event["event_type"],
                        event["account"],
                        float(event["amount_kzt"]),
                        event.get("store_code"),
                        event.get("ref_type"),
                        event.get("ref_id"),
                        event.get("notes"),
                        event.get("source"),
                        event.get("run_id"),
                        event.get("event_hash"),
                    ),
                )
            conn.commit()

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text("\n".join(report_lines) + "\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import manual balance check events")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to bank_accounts.yaml")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--apply", action="store_true", help="Apply writes (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_balance_checks(args.config, args.db, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
