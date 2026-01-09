#!/usr/bin/env python3
"""Transfer ledger CLI."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.transfer_ledger import repository
from core.transfer_ledger import service


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Transfer ledger CLI")
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_po = sub.add_parser("post-po", help="Post supplier payment (CNY)")
    p_po.add_argument("po_id")
    p_po.add_argument("amount_cny", type=float)
    p_po.add_argument("fx_rate_cny_kzt", type=float)
    p_po.add_argument("--date", type=_parse_date, dest="paid_at")
    p_po.add_argument("--source", default="MANUAL")
    p_po.add_argument("--notes", default="")

    p_cargo = sub.add_parser("post-cargo", help="Post cargo payment (USD)")
    p_cargo.add_argument("po_id")
    p_cargo.add_argument("amount_usd", type=float)
    p_cargo.add_argument("fx_rate_usd_kzt", type=float)
    p_cargo.add_argument("--date", type=_parse_date, dest="paid_at")
    p_cargo.add_argument("--source", default="MANUAL")
    p_cargo.add_argument("--notes", default="")

    p_tr = sub.add_parser("post-transfer", help="Post internal transfer")
    p_tr.add_argument("amount", type=float)
    p_tr.add_argument("currency")
    p_tr.add_argument("fx_rate_to_kzt", type=float)
    p_tr.add_argument("from_account")
    p_tr.add_argument("to_account")
    p_tr.add_argument("--date", type=_parse_date, dest="paid_at")
    p_tr.add_argument("--source", default="MANUAL")
    p_tr.add_argument("--notes", default="")
    p_tr.add_argument("--reference-id", default=None)

    p_list = sub.add_parser("list", help="List ledger entries")
    p_list.add_argument("--reference-type", default=None)
    p_list.add_argument("--reference-id", default=None)
    p_list.add_argument("--currency", default=None)
    p_list.add_argument("--limit", type=int, default=None)

    p_bal = sub.add_parser("balance", help="Get balance")
    p_bal.add_argument("--currency", default="KZT")
    p_bal.add_argument("--as-of", type=_parse_date, dest="as_of")

    args = parser.parse_args()

    if args.cmd == "post-po":
        entry_id = service.post_po_payment_cny(
            args.po_id,
            args.amount_cny,
            args.fx_rate_cny_kzt,
            paid_at=args.paid_at,
            source=args.source,
            notes=args.notes,
            db_path=args.db,
        )
        print(f"OK entry_id={entry_id}")
        return 0

    if args.cmd == "post-cargo":
        entry_id = service.post_cargo_payment_usd(
            args.po_id,
            args.amount_usd,
            args.fx_rate_usd_kzt,
            paid_at=args.paid_at,
            source=args.source,
            notes=args.notes,
            db_path=args.db,
        )
        print(f"OK entry_id={entry_id}")
        return 0

    if args.cmd == "post-transfer":
        entry_id = service.post_transfer(
            args.amount,
            args.currency,
            args.fx_rate_to_kzt,
            args.from_account,
            args.to_account,
            paid_at=args.paid_at,
            source=args.source,
            notes=args.notes,
            reference_id=args.reference_id,
            db_path=args.db,
        )
        print(f"OK entry_id={entry_id}")
        return 0

    if args.cmd == "list":
        entries = repository.list_entries(
            reference_type=args.reference_type,
            reference_id=args.reference_id,
            currency=args.currency,
            limit=args.limit,
            db_path=args.db,
        )
        for e in entries:
            print(
                f"{e.entry_id} {e.entry_date} {e.amount} {e.currency} "
                f"(kzt={e.amount_kzt}) {e.reference_type}:{e.reference_id}"
            )
        return 0

    if args.cmd == "balance":
        total = repository.get_balance(
            currency=args.currency,
            as_of_date=args.as_of,
            db_path=args.db,
        )
        print(f"{args.currency.upper()} balance: {total}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
