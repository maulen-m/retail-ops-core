#!/usr/bin/env python3
"""
Backfill missing sku/size fields in fact_orders_kaspi from kaspi_orders_y.

Uses kaspi_orders_y as archive truth for order line details.
If an order has multiple archive lines, it updates the existing row with the
first line and inserts additional rows for the remaining lines.

Idempotent: skips rows that already have sku_id + my_size.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill fact_orders_kaspi sizes from kaspi_orders_y")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--cutoff-date", type=str, default=None, help="Only orders planned <= date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--fill-missing",
        action="store_true",
        help="Assign placeholder size for archive orders with no match (assigned_size='UNKNOWN')",
    )
    args = parser.parse_args()

    cutoff_date = _parse_date(args.cutoff_date) if args.cutoff_date else None

    with get_db(args.db) as conn:
        if not _table_exists(conn, "fact_orders_kaspi"):
            print("ERROR: Missing table fact_orders_kaspi")
            return 1
        if not _table_exists(conn, "kaspi_orders_y"):
            print("ERROR: Missing table kaspi_orders_y")
            return 1

        base_query = """
            SELECT id, order_id, store_code, planned_shipment_date,
                   internal_status, kaspi_status, channel_code,
                   unit_price_kzt, source, source_file, created_at
            FROM fact_orders_kaspi
            WHERE (sku_id IS NULL OR sku_id = '' OR my_size IS NULL OR my_size = '')
        """
        params = []
        if cutoff_date:
            base_query += " AND planned_shipment_date IS NOT NULL AND planned_shipment_date <= ?"
            params.append(cutoff_date.isoformat())

        rows = conn.execute(base_query, params).fetchall()
        updated = 0
        inserted = 0
        skipped = 0
        filled_unknown = 0

        for row in rows:
            order_id = row["order_id"]
            store_code = row["store_code"]
            y_rows = conn.execute(
                """
                SELECT order_id, store_code, kaspi_offer_name, planned_shipment_date,
                       quantity, unit_price_kzt, kaspi_status, sku_key, sku_id, my_size
                FROM kaspi_orders_y
                WHERE order_id = ? AND store_code = ?
                ORDER BY kaspi_offer_name
                """,
                (order_id, store_code),
            ).fetchall()
            if not y_rows:
                if args.fill_missing and row["kaspi_status"] and str(row["kaspi_status"]).strip().upper() == "ARCHIVE":
                    if not args.dry_run:
                        conn.execute(
                            """
                            UPDATE fact_orders_kaspi
                            SET assigned_size = COALESCE(assigned_size, 'UNKNOWN'),
                                size_source = COALESCE(size_source, 'ARCHIVE_MISSING'),
                                size_confidence = COALESCE(size_confidence, 'LOW'),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (row["id"],),
                        )
                    filled_unknown += 1
                else:
                    skipped += 1
                continue

            base = y_rows[0]
            # If a sized row already exists for this order/sku, drop the empty row.
            exists = conn.execute(
                """
                SELECT 1
                FROM fact_orders_kaspi
                WHERE order_id = ? AND store_code = ? AND sku_id = ?
                  AND id != ?
                """,
                (order_id, store_code, base["sku_id"], row["id"]),
            ).fetchone()
            if exists:
                if not args.dry_run:
                    conn.execute("DELETE FROM fact_orders_kaspi WHERE id = ?", (row["id"],))
                updated += 1
            else:
                if not args.dry_run:
                    conn.execute(
                        """
                        UPDATE fact_orders_kaspi
                        SET kaspi_offer_name = COALESCE(kaspi_offer_name, ?),
                            sku_key = COALESCE(sku_key, ?),
                            sku_id = COALESCE(sku_id, ?),
                            my_size = COALESCE(my_size, ?),
                            assigned_size = COALESCE(assigned_size, ?),
                            size_source = COALESCE(size_source, 'ARCHIVE_BACKFILL'),
                            size_confidence = COALESCE(size_confidence, 'HIGH'),
                            planned_shipment_date = COALESCE(planned_shipment_date, ?),
                            unit_price_kzt = COALESCE(unit_price_kzt, ?),
                            kaspi_status = COALESCE(kaspi_status, ?),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            base["kaspi_offer_name"],
                            base["sku_key"],
                            base["sku_id"],
                            base["my_size"],
                            base["my_size"],
                            base["planned_shipment_date"],
                            base["unit_price_kzt"],
                            base["kaspi_status"],
                            row["id"],
                        ),
                    )
                updated += 1

            if len(y_rows) > 1:
                for extra in y_rows[1:]:
                    exists = conn.execute(
                        """
                        SELECT 1
                        FROM fact_orders_kaspi
                        WHERE order_id = ? AND store_code = ? AND sku_id = ?
                        """,
                        (order_id, store_code, extra["sku_id"]),
                    ).fetchone()
                    if exists:
                        continue
                    if args.dry_run:
                        inserted += 1
                        continue
                    conn.execute(
                        """
                        INSERT INTO fact_orders_kaspi (
                            order_id, store_code, channel_code,
                            kaspi_offer_name, sku_key, sku_id, my_size,
                            quantity, unit_price_kzt, planned_shipment_date,
                            kaspi_status, internal_status, source, source_file,
                            assigned_size, size_source, size_confidence, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            order_id,
                            store_code,
                            row["channel_code"],
                            extra["kaspi_offer_name"],
                            extra["sku_key"],
                            extra["sku_id"],
                            extra["my_size"],
                            extra["quantity"] or 1,
                            extra["unit_price_kzt"] or row["unit_price_kzt"],
                            row["planned_shipment_date"] or extra["planned_shipment_date"],
                            extra["kaspi_status"] or row["kaspi_status"],
                            row["internal_status"],
                            row["source"],
                            row["source_file"],
                            extra["my_size"],
                            "ARCHIVE_BACKFILL",
                            "HIGH",
                            row["created_at"],
                        ),
                    )
                    inserted += 1

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

    print(f"Updated rows: {updated}")
    print(f"Inserted rows: {inserted}")
    print(f"Skipped rows (no archive match): {skipped}")
    if filled_unknown:
        print(f"Filled unknown sizes: {filled_unknown}")
    if args.dry_run:
        print("Dry run: no DB writes performed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
