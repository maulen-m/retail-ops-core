#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "db" / "app.db"


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


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def dedupe_order_events(db_path: Path, apply: bool, run_id: str | None) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    if apply and os.getenv("ENABLE_CASHFLOW_WRITE") != "1":
        raise RuntimeError("Refusing to apply without ENABLE_CASHFLOW_WRITE=1")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing")

        rows = conn.execute(
            """
            SELECT rowid,
                   event_date,
                   event_type,
                   account,
                   amount_kzt,
                   store_code,
                   sku_key,
                   sku_id,
                   ref_type,
                   ref_id
            FROM fact_cashflow_events
            WHERE ref_type = 'ORDER'
              AND event_type IN ('CASH_IN', 'COGS_RECOGNIZED')
            ORDER BY ref_id, event_type, event_date, rowid
            """
        ).fetchall()

        groups: dict[tuple, list[sqlite3.Row]] = {}
        for row in rows:
            key = (
                str(row["ref_id"]) if row["ref_id"] is not None else "",
                row["event_type"],
                row["account"],
                float(row["amount_kzt"] or 0.0),
                row["store_code"],
                row["sku_key"],
                row["sku_id"],
            )
            groups.setdefault(key, []).append(row)

        reversals = []
        for key, items in groups.items():
            if len(items) <= 1:
                continue
            # Keep the earliest event_date row; reverse each subsequent duplicate.
            for dup in items[1:]:
                reversals.append(
                    {
                        "event_date": dup["event_date"],
                        "event_type": dup["event_type"],
                        "account": dup["account"],
                        "amount_kzt": -float(dup["amount_kzt"] or 0.0),
                        "store_code": dup["store_code"],
                        "sku_key": dup["sku_key"],
                        "sku_id": dup["sku_id"],
                        "ref_type": dup["ref_type"],
                        "ref_id": dup["ref_id"],
                        "notes": "DEDUP reversal",
                        "source": "ORDER_DEDUP",
                        "run_id": run_id or datetime.now().strftime("%Y%m%d_%H%M%S"),
                    }
                )

        if not reversals:
            return 0

        for event in reversals:
            event["event_hash"] = _event_hash(event)

        existing_hashes = {
            row[0]
            for row in conn.execute(
                "SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({})".format(
                    ",".join("?" * len(reversals))
                ),
                [e["event_hash"] for e in reversals],
            ).fetchall()
        }
        new_events = [e for e in reversals if e["event_hash"] not in existing_hashes]

        if apply and new_events:
            conn.executemany(
                """
                INSERT INTO fact_cashflow_events (
                    event_date, event_type, account, amount_kzt,
                    store_code, sku_key, sku_id, ref_type, ref_id,
                    notes, source, run_id, event_hash
                ) VALUES (
                    :event_date, :event_type, :account, :amount_kzt,
                    :store_code, :sku_key, :sku_id, :ref_type, :ref_id,
                    :notes, :source, :run_id, :event_hash
                )
                """,
                new_events,
            )
            conn.commit()

        return len(new_events)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deduplicate cashflow order events.")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    added = dedupe_order_events(Path(args.db), apply=args.apply, run_id=args.run_id)
    print(f"Dedup reversal events added: {added}")
    if not args.apply:
        print("DRY RUN: no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
