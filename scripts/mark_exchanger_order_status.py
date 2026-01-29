#!/usr/bin/env python3
"""Manually override exchanger order status and record an event."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.transfer_ledger.repository import ensure_schema


def _pick_order(cur, exchanger_order_id: str | None, order_id: str | None):
    if exchanger_order_id:
        row = cur.execute(
            """
            SELECT exchanger_order_id, exchanger, order_id, status, subject, message_date
            FROM exchanger_orders
            WHERE exchanger_order_id = ?
            """,
            (exchanger_order_id,),
        ).fetchone()
        return row

    if order_id:
        rows = cur.execute(
            """
            SELECT exchanger_order_id, exchanger, order_id, status, subject, message_date
            FROM exchanger_orders
            WHERE order_id = ?
            ORDER BY message_date DESC
            """,
            (order_id,),
        ).fetchall()
        if not rows:
            return None
        return rows[0]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual exchanger order status override")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--order-id", dest="order_id", help="Numeric exchanger order id")
    parser.add_argument("--exchanger-order-id", dest="exchanger_order_id", help="Full exchanger_order_id")
    parser.add_argument("--status", required=True, help="New status (e.g., CANCELLED, COMPLETED)")
    parser.add_argument("--note", default="", help="Audit note for manual override")
    parser.add_argument("--source", default="MANUAL", help="Event source label")
    parser.add_argument("--dry-run", action="store_true", help="Print intended changes only")
    args = parser.parse_args()

    if not args.order_id and not args.exchanger_order_id:
        print("ERROR: --order-id or --exchanger-order-id is required.", file=sys.stderr)
        return 1

    ensure_schema(args.db)
    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    row = _pick_order(cur, args.exchanger_order_id, args.order_id)
    if not row:
        print("ERROR: exchanger order not found.", file=sys.stderr)
        return 1

    exchanger_order_id = row["exchanger_order_id"]
    exchanger = row["exchanger"]
    order_id = row["order_id"]
    prev_status = row["status"]
    subject = row["subject"] or "Manual override"

    new_status = args.status.strip().upper()
    now = datetime.now(timezone.utc).isoformat()
    event_id = f"manual-override-{exchanger_order_id}-{now}"

    payload = {
        "manual": True,
        "note": args.note,
        "prev_status": prev_status,
        "new_status": new_status,
        "set_at": now,
    }

    if args.dry_run:
        print(f"[dry-run] exchanger_order_id={exchanger_order_id}")
        print(f"[dry-run] status: {prev_status} -> {new_status}")
        print(f"[dry-run] note: {args.note}")
        return 0

    cur.execute(
        """
        UPDATE exchanger_orders
        SET status = ?, updated_at = datetime('now')
        WHERE exchanger_order_id = ?
        """,
        (new_status, exchanger_order_id),
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO exchanger_order_events (
            exchanger_order_id, exchanger, order_id, status,
            message_id, message_date, subject, raw_json, source, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            exchanger_order_id,
            exchanger,
            order_id,
            new_status,
            event_id,
            now,
            subject,
            json.dumps(payload),
            args.source,
        ),
    )
    conn.commit()
    conn.close()

    print(f"OK: {exchanger_order_id} status={new_status} (prev={prev_status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
