#!/usr/bin/env python3
"""
Translate transfer_ledger entries into cashflow events.

Default: DRY RUN (no DB writes). Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "app.db"


def _normalize_date(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _event_hash(event: dict) -> str:
    parts = [
        _normalize_date(event.get("event_date")),
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


def _load_statement_keys(conn: sqlite3.Connection) -> set[tuple[str, str, float]]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT event_date, account, amount_kzt
        FROM fact_cashflow_events
        WHERE ref_type = 'MT940'
        """
    ).fetchall()
    return {(row[0], row[1], float(row[2] or 0.0)) for row in rows}


def _load_existing_keys(conn: sqlite3.Connection) -> set[tuple]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return set()
    rows = conn.execute(
        """
        SELECT event_date, event_type, account, amount_kzt, ref_type, ref_id
        FROM fact_cashflow_events
        """
    ).fetchall()
    return {
        (
            row[0],
            row[1],
            row[2],
            float(row[3] or 0.0),
            row[4],
            row[5],
        )
        for row in rows
    }


def _load_existing_hashes(conn: sqlite3.Connection, events: list[dict]) -> set[str]:
    if not events:
        return set()
    placeholders = ",".join("?" * len(events))
    hashes = [e["event_hash"] for e in events]
    rows = conn.execute(
        f"SELECT event_hash FROM fact_cashflow_events WHERE event_hash IN ({placeholders})",
        hashes,
    ).fetchall()
    return {row[0] for row in rows}


def _load_allocations(conn: sqlite3.Connection, entry_id: int) -> list[dict]:
    if not _table_exists(conn, "po_funding_allocations"):
        return []
    rows = conn.execute(
        """
        SELECT po_id, amount_kzt
        FROM po_funding_allocations
        WHERE entry_id = ?
        """,
        (entry_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def import_transfer_ledger(
    db_path: Path,
    since: Optional[date],
    until: Optional[date],
    apply: bool,
    run_id: Optional[str],
) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    if apply and os.getenv("ENABLE_CASHFLOW_WRITE") != "1":
        raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "transfer_ledger"):
            raise RuntimeError("transfer_ledger missing")
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        clauses = []
        params = []
        if since:
            clauses.append("date(entry_date) >= ?")
            params.append(since.isoformat())
        if until:
            clauses.append("date(entry_date) <= ?")
            params.append(until.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        rows = conn.execute(
            f"""
            SELECT entry_id, entry_date, amount_kzt, currency, reference_type, reference_id,
                   from_account, to_account, notes
            FROM transfer_ledger
            {where}
            ORDER BY entry_date, entry_id
            """,
            params,
        ).fetchall()

        statement_keys = _load_statement_keys(conn)
        existing_keys = _load_existing_keys(conn)

        events: list[dict] = []

        for row in rows:
            entry_id = row["entry_id"]
            entry_date = row["entry_date"]
            amount_kzt = float(row["amount_kzt"] or 0.0)
            ref_type = row["reference_type"]
            ref_id = row["reference_id"]
            notes = row["notes"] or ""

            allocations = _load_allocations(conn, entry_id)

            def add_event(event: dict) -> None:
                key = (
                    _normalize_date(event["event_date"]),
                    event["event_type"],
                    event["account"],
                    float(event["amount_kzt"] or 0.0),
                    event["ref_type"],
                    event["ref_id"],
                )
                if key in existing_keys:
                    return
                if (
                    event["account"] == "CASH"
                    and (event["event_date"], event["account"], float(event["amount_kzt"] or 0.0))
                    in statement_keys
                ):
                    return
                events.append(event)
                existing_keys.add(key)

            if allocations:
                for alloc in allocations:
                    alloc_kzt = abs(float(alloc["amount_kzt"] or 0.0))
                    add_event(
                        {
                            "event_date": entry_date,
                            "event_type": "PO_PAYMENT",
                            "account": "CASH",
                            "amount_kzt": -alloc_kzt,
                            "store_code": None,
                            "sku_key": None,
                            "sku_id": None,
                            "ref_type": "PO",
                            "ref_id": alloc["po_id"],
                            "notes": f"transfer_entry={entry_id}",
                            "source": "TRANSFER_LEDGER",
                            "run_id": run_id,
                        }
                    )
                    add_event(
                        {
                            "event_date": entry_date,
                            "event_type": "INVENTORY_INBOUND",
                            "account": "INVENTORY_INBOUND_COST",
                            "amount_kzt": alloc_kzt,
                            "store_code": None,
                            "sku_key": None,
                            "sku_id": None,
                            "ref_type": "PO",
                            "ref_id": alloc["po_id"],
                            "notes": f"transfer_entry={entry_id}",
                            "source": "TRANSFER_LEDGER",
                            "run_id": run_id,
                        }
                    )
                continue

            if ref_type in {"PO", "CARGO"}:
                pay_type = "PO_PAYMENT" if ref_type == "PO" else "CARGO_PAYMENT"
                amount = abs(amount_kzt)
                add_event(
                    {
                        "event_date": entry_date,
                        "event_type": pay_type,
                        "account": "CASH",
                        "amount_kzt": -amount,
                        "store_code": None,
                        "sku_key": None,
                        "sku_id": None,
                        "ref_type": "PO",
                        "ref_id": ref_id,
                        "notes": notes,
                        "source": "TRANSFER_LEDGER",
                        "run_id": run_id,
                    }
                )
                add_event(
                    {
                        "event_date": entry_date,
                        "event_type": "INVENTORY_INBOUND",
                        "account": "INVENTORY_INBOUND_COST",
                        "amount_kzt": amount,
                        "store_code": None,
                        "sku_key": None,
                        "sku_id": None,
                        "ref_type": "PO",
                        "ref_id": ref_id,
                        "notes": notes,
                        "source": "TRANSFER_LEDGER",
                        "run_id": run_id,
                    }
                )
                continue

            if ref_type == "TRANSFER":
                amount = abs(amount_kzt)
                add_event(
                    {
                        "event_date": entry_date,
                        "event_type": "CASH_RECLASS",
                        "account": "CASH",
                        "amount_kzt": -amount,
                        "store_code": None,
                        "sku_key": None,
                        "sku_id": None,
                        "ref_type": "TRANSFER",
                        "ref_id": ref_id,
                        "notes": f"{row['from_account']}->{row['to_account']} {notes}".strip(),
                        "source": "TRANSFER_LEDGER",
                        "run_id": run_id,
                    }
                )
                add_event(
                    {
                        "event_date": entry_date,
                        "event_type": "CASH_RECLASS",
                        "account": "CASH",
                        "amount_kzt": amount,
                        "store_code": None,
                        "sku_key": None,
                        "sku_id": None,
                        "ref_type": "TRANSFER",
                        "ref_id": ref_id,
                        "notes": f"{row['from_account']}->{row['to_account']} {notes}".strip(),
                        "source": "TRANSFER_LEDGER",
                        "run_id": run_id,
                    }
                )
                continue

            # default: record as cash transfer (no inventory impact)
            add_event(
                {
                    "event_date": entry_date,
                    "event_type": "CASH_TRANSFER",
                    "account": "CASH",
                    "amount_kzt": amount_kzt,
                    "store_code": None,
                    "sku_key": None,
                    "sku_id": None,
                    "ref_type": ref_type,
                    "ref_id": ref_id,
                    "notes": notes,
                    "source": "TRANSFER_LEDGER",
                    "run_id": run_id,
                }
            )

        if not events:
            return 0

        for event in events:
            event["event_hash"] = _event_hash(event)

        existing_hashes = _load_existing_hashes(conn, events)
        to_insert = [e for e in events if e["event_hash"] not in existing_hashes]

        if apply and to_insert:
            conn.executemany(
                """
                INSERT OR IGNORE INTO fact_cashflow_events (
                    event_date, event_type, account, amount_kzt,
                    store_code, sku_key, sku_id, ref_type, ref_id,
                    notes, source, run_id, event_hash
                ) VALUES (
                    :event_date, :event_type, :account, :amount_kzt,
                    :store_code, :sku_key, :sku_id, :ref_type, :ref_id,
                    :notes, :source, :run_id, :event_hash
                )
                """,
                to_insert,
            )
            conn.commit()

        return len(to_insert)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import transfer ledger into cashflow events")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--until", type=str, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()

    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None

    added = import_transfer_ledger(Path(args.db), since=since, until=until, apply=args.apply, run_id=args.run_id)
    print(f"Transfer ledger events added: {added}")
    if not args.apply:
        print("DRY RUN: no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
