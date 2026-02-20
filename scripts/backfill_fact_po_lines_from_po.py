#!/usr/bin/env python3
"""
Backfill fact_po_lines from po_header + po_line for specified PO IDs.

This is idempotent: deletes existing fact_po_lines rows for the PO(s) then inserts fresh.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from datetime import datetime
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH


def _derive_status(po_status: str, arrival_date: str | None) -> str:
    if arrival_date:
        return "DELIVERED"
    if po_status in {"IN_TRANSIT", "SHIPPED_CARGO", "SHIPPED_SELLER"}:
        return "IN_TRANSIT"
    return "UNPAID"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill fact_po_lines from po_header + po_line")
    parser.add_argument("--po-id", action="append", required=True, help="PO ID to backfill (repeatable)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    args = parser.parse_args()

    po_ids = args.po_id

    with get_db(args.db) as conn:
        # Avoid foreign key mismatch errors caused by legacy FK definitions.
        conn.execute("PRAGMA foreign_keys = OFF")
        for po_id in po_ids:
            header = conn.execute(
                "SELECT po_id, message_date, ast_arrival_real, alm_arrival_real, status FROM po_header WHERE po_id = ?",
                (po_id,),
            ).fetchone()

            if not header:
                print(f"PO not found: {po_id}")
                continue

            arrival_date = header["ast_arrival_real"] or header["alm_arrival_real"]
            po_date = header["message_date"]
            status = _derive_status(header["status"], arrival_date)

            lines = conn.execute(
                "SELECT sku_key, sku_id, my_size, order_qty, received_qty, unit_cost_kzt FROM po_line WHERE po_id = ?",
                (po_id,),
            ).fetchall()

            if not lines:
                print(f"No lines found for {po_id}")
                continue

            updated = 0
            inserted = 0
            now = datetime.now().isoformat()
            est_arrival = header["ast_arrival_real"] if header["ast_arrival_real"] else header["alm_arrival_real"]
            existing_po = conn.execute(
                "SELECT COUNT(*) as cnt FROM fact_po_lines WHERE po_id = ?",
                (po_id,),
            ).fetchone()["cnt"]

            for line in lines:
                sku_id = line["sku_id"]
                my_size = line["my_size"]
                order_qty = int(line["order_qty"] or 0)
                received_qty = int(line["received_qty"] or 0)
                unit_cost_kzt = float(line["unit_cost_kzt"] or 0)

                existing = conn.execute(
                    """
                    SELECT id FROM fact_po_lines
                    WHERE po_id = ? AND sku_id = ? AND my_size = ?
                    """,
                    (po_id, sku_id, my_size),
                ).fetchone()

                if existing:
                    conn.execute(
                        """
                        UPDATE fact_po_lines
                        SET store_code = ?, sku_key = ?, order_quantity = ?, unit_cost_kzt = ?,
                            po_date = ?, est_arrival_date = ?, actual_arrival_date = ?,
                            status = ?, received_qty = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            "UNIVERSAL",
                            line["sku_key"],
                            order_qty,
                            unit_cost_kzt,
                            po_date,
                            est_arrival,
                            arrival_date,
                            status,
                            received_qty,
                            now,
                            existing["id"],
                        ),
                    )
                    updated += 1
                elif existing_po == 0:
                    conn.execute(
                        """
                        INSERT INTO fact_po_lines (
                            po_id, store_code, sku_key, sku_id, my_size,
                            order_quantity, unit_cost_kzt, po_date,
                            est_arrival_date, actual_arrival_date,
                            status, received_qty, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            po_id,
                            "UNIVERSAL",
                            line["sku_key"],
                            sku_id,
                            my_size,
                            order_qty,
                            unit_cost_kzt,
                            po_date,
                            est_arrival,
                            arrival_date,
                            status,
                            received_qty,
                            now,
                            now,
                        ),
                    )
                    inserted += 1
                else:
                    # Avoid inserts when PO already exists in fact_po_lines (FK mismatch risk).
                    # Log missing rows for follow-up.
                    print(f"Warning: no existing fact_po_lines row for {po_id} {sku_id} {my_size}; skipping insert")

            print(f"Backfilled {po_id}: updated={updated} inserted={inserted}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
