#!/usr/bin/env python3
"""
Sync delivered PO arrivals into the stock ledger.

Idempotent: only inserts missing INBOUND ledger events per PO line.
"""

from __future__ import annotations

import argparse
from datetime import datetime, date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.db.ledger import add_ledger_event


def _parse_date(value: str | None) -> str:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    return date.today().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync delivered PO arrivals to stock ledger")
    parser.add_argument("--snapshot-date", help="Cutoff date YYYY-MM-DD (default: today)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply ledger inserts (default: dry-run)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Insert full received_qty even if prior PO ledger events exist",
    )
    args = parser.parse_args()

    snapshot_date = _parse_date(args.snapshot_date)

    with get_db(args.db) as conn:
        rows = conn.execute(
            """
            SELECT po_id, sku_id, sku_key, my_size, received_qty, actual_arrival_date
            FROM fact_po_lines
            WHERE status = 'DELIVERED'
              AND actual_arrival_date IS NOT NULL
              AND actual_arrival_date <= ?
              AND COALESCE(received_qty, 0) > 0
            """,
            (snapshot_date,),
        ).fetchall()

        inserted = 0
        units = 0
        for row in rows:
            po_id = row["po_id"]
            sku_id = row["sku_id"]
            sku_key = row["sku_key"]
            my_size = row["my_size"]
            received_qty = int(row["received_qty"] or 0)
            arrival_date = row["actual_arrival_date"]

            if received_qty <= 0:
                continue

            existing = 0
            if not args.force:
                existing = conn.execute(
                    """
                    SELECT COALESCE(SUM(qty_change), 0) as qty
                    FROM stock_ledger
                    WHERE event_type = 'INBOUND'
                      AND reference_type = 'PO'
                      AND reference_id = ?
                      AND sku_id = ?
                      AND my_size = ?
                    """,
                    (po_id, sku_id, my_size),
                ).fetchone()["qty"] or 0

            to_add = received_qty - existing
            if to_add <= 0:
                continue

            inserted += 1
            units += to_add
            if args.apply:
                add_ledger_event(
                    event_type="INBOUND",
                    sku_id=sku_id,
                    qty_change=to_add,
                    event_date=datetime.strptime(arrival_date, "%Y-%m-%d").date(),
                    sku_key=sku_key,
                    my_size=my_size,
                    reference_id=po_id,
                    reference_type="PO",
                    notes="Backfill PO arrival from fact_po_lines",
                    input_source="SYSTEM",
                    created_by="system",
                    db_path=args.db,
                )

        if not args.apply:
            conn.rollback()

    print(f"Snapshot: {snapshot_date}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Ledger events inserted: {inserted}")
    print(f"Units added: {units}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
