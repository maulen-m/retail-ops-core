#!/usr/bin/env python3
"""
Import manual cash balance checks and create adjustment events.

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_CSV = PROJECT_ROOT / "data" / "cashflow" / "cash_balance_checks.csv"


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
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def import_balance_checks(csv_path: Path, db_path: Path, apply: bool, run_id: str) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")
        if not _table_exists(conn, "fact_cashflow_daily"):
            raise RuntimeError("fact_cashflow_daily missing; run rebuild_cashflow_calendar.py --apply")

        reader = csv.DictReader(csv_path.open("r", newline=""))
        required = {"date", "cash_balance_kzt"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV missing required columns: {required}")

        events = []
        for row in reader:
            day = (row.get("date") or "").strip()
            if not day:
                continue
            amount = float(str(row.get("cash_balance_kzt") or 0).replace(",", ""))
            current = conn.execute(
                "SELECT cash_close FROM fact_cashflow_daily WHERE date = ?",
                (day,),
            ).fetchone()
            if not current:
                raise RuntimeError(f"No cashflow daily row for {day}; rebuild calendar first.")
            delta = round(amount - float(current["cash_close"] or 0.0), 2)
            if delta == 0:
                continue
            event = {
                "event_date": day,
                "event_type": "CASH_ADJUSTMENT",
                "account": "CASH",
                "amount_kzt": delta,
                "notes": row.get("notes") or "manual cash balance check",
                "source": row.get("source") or "MANUAL",
                "run_id": run_id,
                "ref_type": "CASH_BALANCE_CHECK",
                "ref_id": day,
            }
            event["event_hash"] = _event_hash(event)
            events.append(event)

        existing = set()
        if events:
            placeholders = ",".join("?" * len(events))
            existing = {
                r[0]
                for r in conn.execute(
                    f"SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({placeholders})",
                    [e["event_hash"] for e in events],
                ).fetchall()
            }

        new_events = [e for e in events if e["event_hash"] not in existing]

        print(f"Rows in CSV: {len(list(csv.DictReader(csv_path.open('r', newline=''))))}")
        print(f"New events: {len(new_events)} (existing skipped: {len(events) - len(new_events)})")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for e in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, notes, source, run_id,
                        ref_type, ref_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e["event_date"],
                        e["event_type"],
                        e["account"],
                        e["amount_kzt"],
                        e["notes"],
                        e["source"],
                        e["run_id"],
                        e["ref_type"],
                        e["ref_id"],
                        e["event_hash"],
                    ),
                )
            conn.commit()
            print("APPLY: inserted cash balance adjustment events.")
        else:
            print("DRY RUN: no DB writes.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import cash balance checks")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_balance_checks(args.csv, args.db, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
