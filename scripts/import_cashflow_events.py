#!/usr/bin/env python3
"""
Import cashflow events from CSV into fact_cashflow_events.

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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _event_hash(row: dict) -> str:
    parts = [
        str(row.get("event_date") or ""),
        str(row.get("event_type") or ""),
        str(row.get("account") or ""),
        f"{float(row.get('amount_kzt') or 0.0):.4f}",
        str(row.get("store_code") or ""),
        str(row.get("sku_key") or ""),
        str(row.get("sku_id") or ""),
        str(row.get("ref_type") or ""),
        str(row.get("ref_id") or ""),
        str(row.get("source") or ""),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_amount(val: str) -> float:
    try:
        return float(str(val).replace(",", "").strip())
    except Exception:
        return 0.0


def import_events(csv_path: Path, db_path: Path, apply: bool, run_id: str) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        reader = csv.DictReader(csv_path.open("r", newline=""))
        required = {"event_date", "event_type", "account", "amount_kzt"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV missing required columns: {required}")

        rows = list(reader)
        to_insert = []
        for row in rows:
            event = {
                "event_date": row.get("event_date"),
                "event_ts": row.get("event_ts"),
                "event_type": row.get("event_type"),
                "account": row.get("account"),
                "amount_kzt": _normalize_amount(row.get("amount_kzt", 0)),
                "store_code": row.get("store_code") or None,
                "sku_key": row.get("sku_key") or None,
                "sku_id": row.get("sku_id") or None,
                "ref_type": row.get("ref_type") or None,
                "ref_id": row.get("ref_id") or None,
                "notes": row.get("notes") or None,
                "source": row.get("source") or "MANUAL",
                "run_id": row.get("run_id") or run_id,
            }
            event["event_hash"] = _event_hash(event)
            to_insert.append(event)

        existing_hashes = {
            row["event_hash"]
            for row in conn.execute(
                "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(
                    ",".join("?" * len(to_insert)) if to_insert else "''"
                ),
                [e["event_hash"] for e in to_insert],
            ).fetchall()
        } if to_insert else set()

        new_events = [e for e in to_insert if e["event_hash"] not in existing_hashes]

        print(f"Rows in CSV: {len(rows)}")
        print(f"New events: {len(new_events)} (existing skipped: {len(to_insert) - len(new_events)})")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for e in new_events:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fact_cashflow_events (
                        event_date, event_ts, event_type, account, amount_kzt,
                        store_code, sku_key, sku_id, ref_type, ref_id, notes,
                        source, run_id, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        e["event_date"],
                        e["event_ts"],
                        e["event_type"],
                        e["account"],
                        e["amount_kzt"],
                        e["store_code"],
                        e["sku_key"],
                        e["sku_id"],
                        e["ref_type"],
                        e["ref_id"],
                        e["notes"],
                        e["source"],
                        e["run_id"],
                        e["event_hash"],
                    ),
                )
            conn.commit()
            print("APPLY: inserted new events.")
        else:
            print("DRY RUN: no DB writes.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import cashflow events from CSV")
    parser.add_argument("csv_path", type=Path, help="Path to CSV file")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--apply", action="store_true", help="Write to DB (requires ENABLE_CASHFLOW_WRITE=1)")
    parser.add_argument("--run-id", type=str, default=None, help="Run id for audit")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_events(args.csv_path, args.db, args.apply, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
