#!/usr/bin/env python3
"""
Clamp negative ledger balances to zero by inserting ADJUSTMENT events.

Idempotent per snapshot date via reference_id.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event


ENV_GATE = "ENABLE_NEGATIVE_LEDGER_CLAMP_WRITE"


def _parse_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _load_existing_adjustments(conn, snapshot_date: str, ref_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT sku_id, sku_key, my_size, qty_change
        FROM stock_ledger
        WHERE event_date = ?
          AND event_type = 'ADJUSTMENT'
          AND reference_id = ?
        """,
        (snapshot_date, ref_id),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_balances_exclusive(conn, snapshot_date: str, store_code: str) -> dict[str, int]:
    params = [snapshot_date]
    store_filter = ""
    if store_code and store_code != "ALL":
        store_filter = "AND store_code = ?"
        params.append(store_code)
    rows = conn.execute(
        f"""
        SELECT sku_id, SUM(qty_change) as balance
        FROM stock_ledger
        WHERE event_date < ?
          {store_filter}
        GROUP BY sku_id
        """,
        params,
    ).fetchall()
    return {row["sku_id"]: row["balance"] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Clamp negative ledger balances to zero")
    parser.add_argument("--snapshot-date", required=True, help="Snapshot date YYYY-MM-DD")
    parser.add_argument("--store-code", default="UNIVERSAL", help="Store code (default: UNIVERSAL = all stores)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply adjustments (default: dry-run)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-clamp even if prior clamp adjustments exist for the snapshot date",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Reverse existing clamp adjustments for the snapshot date before applying new ones",
    )
    args = parser.parse_args()

    if args.apply and os.environ.get(ENV_GATE) != "1":
        raise RuntimeError(f"{ENV_GATE}=1 is required for --apply")

    snapshot_date = _parse_date(args.snapshot_date)
    ref_id = f"NEGATIVE_CLAMP_{snapshot_date}"
    adjust_date = (datetime.strptime(snapshot_date, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()

    with get_db(args.db) as conn:
        existing_rows = _load_existing_adjustments(conn, snapshot_date, ref_id)
        existing = {row["sku_id"] for row in existing_rows}
        if args.replace and existing_rows:
            rev_id = f"{ref_id}_REV"
            existing_rev = _load_existing_adjustments(conn, snapshot_date, rev_id)
            if not existing_rev:
                for row in existing_rows:
                    if args.apply:
                        add_ledger_event(
                            event_type="ADJUSTMENT",
                            sku_id=row["sku_id"],
                            qty_change=-int(row["qty_change"] or 0),
                            event_date=snapshot_date,
                            store_code=args.store_code,
                            reference_id=rev_id,
                            reference_type="ADJUSTMENT",
                            notes=f"Reverse clamp for {snapshot_date}",
                            input_source="SYSTEM",
                            created_by="system",
                            db_path=args.db,
                        )
            existing = set()

        if args.force:
            existing = set()

        balances = _load_balances_exclusive(conn, snapshot_date, args.store_code)

        negatives = {sku_id: bal for sku_id, bal in balances.items() if bal < 0}
        applied = 0
        units = 0

        for sku_id, balance in sorted(negatives.items(), key=lambda x: x[1]):
            if sku_id in existing:
                continue
            qty_change = -balance
            units += qty_change
            applied += 1
            if args.apply:
                add_ledger_event(
                    event_type="ADJUSTMENT",
                    sku_id=sku_id,
                    qty_change=qty_change,
                    event_date=adjust_date,
                    store_code="UNIVERSAL",
                    reference_id=ref_id,
                    reference_type="ADJUSTMENT",
                    notes=f"Clamp negative balance to zero as-of {snapshot_date} (morning)",
                    input_source="SYSTEM",
                    created_by="system",
                    db_path=args.db,
                )

        if not args.apply:
            conn.rollback()

    print(f"Snapshot: {snapshot_date}")
    print(f"Store: {args.store_code}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Negatives found: {len(negatives)}")
    print(f"Adjustments inserted: {applied}")
    print(f"Units adjusted: {units}")
    print(f"Reference ID: {ref_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
