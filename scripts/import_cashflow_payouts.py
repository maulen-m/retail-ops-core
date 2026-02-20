#!/usr/bin/env python3
"""
Import payout events (dual-entry):
- PAYOUT_RECEIVED -> CASH (positive)
- RECEIVABLES_SETTLED -> RECEIVABLES (negative)

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
EXPORT_PATH = PROJECT_ROOT / "exports" / "payout_import_report.txt"


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
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_amount(value: str | None) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def import_payouts(csv_path: Path, db_path: Path, apply: bool, run_id: str) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    report = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        reader = csv.DictReader(csv_path.open("r", newline=""))
        required = {"event_date", "amount_kzt"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV missing required columns: {required}")

        rows = [r for r in reader if not (r.get("event_date", "").startswith("#"))]
        to_insert = []

        for row in rows:
            event_date = (row.get("event_date") or "").strip()
            amount = _normalize_amount(row.get("amount_kzt"))
            ref_id = row.get("ref_id") or None
            notes = row.get("notes") or None
            source = row.get("source") or "MANUAL"
            if not event_date or amount == 0:
                continue

            cash_event = {
                "event_date": event_date,
                "event_type": "PAYOUT_RECEIVED",
                "account": "CASH",
                "amount_kzt": abs(amount),
                "ref_id": ref_id,
                "notes": notes,
                "source": source,
                "run_id": run_id,
            }
            recv_event = {
                "event_date": event_date,
                "event_type": "RECEIVABLES_SETTLED",
                "account": "RECEIVABLES",
                "amount_kzt": -abs(amount),
                "ref_id": ref_id,
                "notes": notes,
                "source": source,
                "run_id": run_id,
            }
            for e in (cash_event, recv_event):
                e["event_hash"] = _event_hash(e)
                to_insert.append(e)

        existing_hashes = set()
        if to_insert:
            existing_hashes = {
                row[0]
                for row in conn.execute(
                    "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(",".join("?" * len(to_insert))
                    ),
                    [e["event_hash"] for e in to_insert],
                ).fetchall()
            }

        new_events = [e for e in to_insert if e["event_hash"] not in existing_hashes]

        report.append(f"Rows in CSV: {len(rows)}")
        report.append(f"New events: {len(new_events)} (existing skipped: {len(to_insert) - len(new_events)})")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for e in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_type, account, amount_kzt, ref_id, notes, source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e["event_date"],
                        e["event_type"],
                        e["account"],
                        e["amount_kzt"],
                        e.get("ref_id"),
                        e.get("notes"),
                        e.get("source"),
                        e.get("run_id"),
                        e["event_hash"],
                    ),
                )
            conn.commit()
            report.append("APPLY: inserted payout events.")
        else:
            report.append("DRY RUN: no DB writes.")

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text("\n".join(report) + "\n")
    print(f"Payout import report: {EXPORT_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import cashflow payouts")
    parser.add_argument("--csv", type=Path, default=PROJECT_ROOT / "data" / "cashflow" / "payouts_import.csv")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_payouts(args.csv, args.db, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
