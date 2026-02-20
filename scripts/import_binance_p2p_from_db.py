#!/usr/bin/env python3
"""Import Binance P2P history from another SQLite DB into current DB (idempotent)."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.transfer_ledger import repository
from core.transfer_ledger.models import LedgerEntry


def _fetch_src_orders(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            order_number, adv_no, trade_type, asset, fiat, fiat_amount, crypto_amount,
            unit_price, order_status, create_time, commission, counterparty,
            advertisement_role, raw_json, source
        FROM binance_c2c_orders
        """
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_src_ledger(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            entry_date, amount, currency, amount_kzt, fx_rate_to_kzt, fx_source,
            reference_type, reference_id, from_account, to_account, notes
        FROM transfer_ledger
        WHERE reference_type = 'BINANCE_P2P'
        """
    ).fetchall()
    return [dict(r) for r in rows]


def import_from_db(src_db: Path, dest_db: Path, apply: bool) -> dict:
    repository.ensure_schema(dest_db)
    with sqlite3.connect(str(src_db)) as conn:
        conn.row_factory = sqlite3.Row
        orders = _fetch_src_orders(conn)
        ledger_rows = _fetch_src_ledger(conn)

    inserted_orders = 0
    inserted_ledger = 0

    if apply:
        for order in orders:
            is_new = repository.upsert_binance_c2c_order(order, db_path=dest_db)
            if is_new:
                inserted_orders += 1
        for row in ledger_rows:
            if repository.has_entry("BINANCE_P2P", row["reference_id"], db_path=dest_db):
                continue
            entry = LedgerEntry(
                entry_id=None,
                entry_date=date.fromisoformat(row["entry_date"]),
                amount=row["amount"],
                currency=row["currency"],
                amount_kzt=row["amount_kzt"],
                fx_rate_to_kzt=row["fx_rate_to_kzt"],
                fx_source=row["fx_source"],
                reference_type=row["reference_type"],
                reference_id=row["reference_id"],
                from_account=row["from_account"] or "",
                to_account=row["to_account"] or "",
                notes=row["notes"] or "",
            )
            repository.insert_entry(entry, db_path=dest_db)
            inserted_ledger += 1

    return {
        "orders_total": len(orders),
        "ledger_total": len(ledger_rows),
        "orders_inserted": inserted_orders,
        "ledger_inserted": inserted_ledger,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Binance P2P history from another DB")
    parser.add_argument("--src-db", type=Path, required=True, help="Source DB with P2P history")
    parser.add_argument("--dest-db", type=Path, default=repository.DEFAULT_DB_PATH, help="Destination DB")
    parser.add_argument("--apply", action="store_true", help="Apply import (default dry-run)")
    args = parser.parse_args()

    if not args.src_db.exists():
        raise FileNotFoundError(f"Source DB not found: {args.src_db}")
    if not args.dest_db.exists():
        raise FileNotFoundError(f"Destination DB not found: {args.dest_db}")

    result = import_from_db(args.src_db, args.dest_db, apply=args.apply)
    print(f"Orders found: {result['orders_total']}")
    print(f"Ledger rows found: {result['ledger_total']}")
    if args.apply:
        print(f"Orders inserted: {result['orders_inserted']}")
        print(f"Ledger entries inserted: {result['ledger_inserted']}")
    else:
        print("Dry run: no changes applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
