#!/usr/bin/env python3
"""
Normalize sku_id/sku_key/my_size across core tables.

Idempotent: updates only when normalization changes values.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import normalize_sku_id, normalize_sku_key, normalize_size, VALID_SIZES


TABLES = [
    "stock_ledger",
    "sales_fact_v2",
    "fact_sales",
    "fact_orders_kaspi",
    "fact_po_lines",
    "po_line",
    "dim_sku_size",
]


def _product_type_from_key(sku_key: str | None) -> str | None:
    if not sku_key:
        return None
    if sku_key.startswith("CL"):
        return "CL"
    return "NON_CL"


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize SKU IDs across tables")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default: dry-run)")
    args = parser.parse_args()

    stats = {}
    with get_db(args.db) as conn:
        if args.apply:
            conn.execute("PRAGMA foreign_keys = OFF")
        for table in TABLES:
            cols = _table_columns(conn, table)
            if "sku_id" not in cols:
                continue

            rows = conn.execute(
                f"SELECT rowid as rid, sku_id, sku_key, my_size FROM {table}"
            ).fetchall()

            updated = 0
            for row in rows:
                sku_id = row["sku_id"]
                sku_key = row["sku_key"] if "sku_key" in cols else None
                my_size = row["my_size"] if "my_size" in cols else None

                normalized_key = normalize_sku_key(sku_key) if sku_key else None
                product_type = _product_type_from_key(normalized_key or sku_key)
                normalized_size = normalize_size(my_size, product_type) if my_size is not None else None
                if product_type and product_type != "CL":
                    normalized_size = "ONE_SIZE"

                normalized_id = normalize_sku_id(sku_id, normalized_key or sku_key)
                if product_type and product_type != "CL" and normalized_key:
                    normalized_id = normalized_key

                changes = {}
                if normalized_key and normalized_key != sku_key:
                    changes["sku_key"] = normalized_key
                if normalized_size and normalized_size != my_size:
                    changes["my_size"] = normalized_size
                if normalized_id and normalized_id != sku_id:
                    changes["sku_id"] = normalized_id

                if not changes:
                    continue

                # Handle potential uniqueness conflicts for dim_sku_size
                if table == "dim_sku_size" and "sku_id" in changes:
                    existing = conn.execute(
                        "SELECT rowid, active_flag FROM dim_sku_size WHERE sku_id = ?",
                        (changes["sku_id"],),
                    ).fetchone()
                    if existing and existing["rowid"] != row["rid"]:
                        if args.apply:
                            if "active_flag" in cols:
                                current_active = conn.execute(
                                    "SELECT active_flag FROM dim_sku_size WHERE rowid = ?",
                                    (row["rid"],),
                                ).fetchone()
                                if current_active and current_active["active_flag"] and not existing["active_flag"]:
                                    conn.execute(
                                        "UPDATE dim_sku_size SET active_flag = 1 WHERE rowid = ?",
                                        (existing["rowid"],),
                                    )
                            conn.execute("DELETE FROM dim_sku_size WHERE rowid = ?", (row["rid"],))
                        updated += 1
                        continue

                # Handle uniqueness conflicts for fact_sales
                if table == "fact_sales" and "sku_id" in changes:
                    existing = conn.execute(
                        """
                        SELECT id, quantity, line_net_rev, cogs_line, profit_line
                        FROM fact_sales
                        WHERE order_id = (SELECT order_id FROM fact_sales WHERE rowid = ?)
                          AND kaspi_offer_name = (SELECT kaspi_offer_name FROM fact_sales WHERE rowid = ?)
                          AND store_code = (SELECT store_code FROM fact_sales WHERE rowid = ?)
                          AND sku_id = ?
                          AND rowid != ?
                        """,
                        (row["rid"], row["rid"], row["rid"], changes["sku_id"], row["rid"]),
                    ).fetchone()
                    if existing:
                        if args.apply:
                            current = conn.execute(
                                """
                                SELECT quantity, line_net_rev, cogs_line, profit_line, sku_key, my_size
                                FROM fact_sales WHERE rowid = ?
                                """,
                                (row["rid"],),
                            ).fetchone()
                            new_quantity = int(existing["quantity"] or 0) + int(current["quantity"] or 0)
                            new_line_net = float(existing["line_net_rev"] or 0) + float(current["line_net_rev"] or 0)
                            new_cogs = float(existing["cogs_line"] or 0) + float(current["cogs_line"] or 0)
                            new_profit = float(existing["profit_line"] or 0) + float(current["profit_line"] or 0)
                            conn.execute(
                                """
                                UPDATE fact_sales
                                SET quantity = ?, line_net_rev = ?, cogs_line = ?, profit_line = ?,
                                    sku_key = ?, my_size = ?
                                WHERE id = ?
                                """,
                                (
                                    new_quantity,
                                    new_line_net,
                                    new_cogs,
                                    new_profit,
                                    normalized_key or current["sku_key"],
                                    normalized_size or current["my_size"],
                                    existing["id"],
                                ),
                            )
                            conn.execute("DELETE FROM fact_sales WHERE rowid = ?", (row["rid"],))
                        updated += 1
                        continue

                # Handle uniqueness conflicts for fact_orders_kaspi
                if table == "fact_orders_kaspi" and "sku_id" in changes:
                    existing = conn.execute(
                        """
                        SELECT id, quantity
                        FROM fact_orders_kaspi
                        WHERE order_id = (SELECT order_id FROM fact_orders_kaspi WHERE rowid = ?)
                          AND store_code = (SELECT store_code FROM fact_orders_kaspi WHERE rowid = ?)
                          AND sku_id = ?
                          AND rowid != ?
                        """,
                        (row["rid"], row["rid"], changes["sku_id"], row["rid"]),
                    ).fetchone()
                    if existing:
                        if args.apply:
                            current = conn.execute(
                                "SELECT quantity, kaspi_offer_name, sku_key, my_size FROM fact_orders_kaspi WHERE rowid = ?",
                                (row["rid"],),
                            ).fetchone()
                            new_qty = int(existing["quantity"] or 0) + int(current["quantity"] or 0)
                            conn.execute(
                                """
                                UPDATE fact_orders_kaspi
                                SET quantity = ?, kaspi_offer_name = ?, sku_key = ?, my_size = ?
                                WHERE id = ?
                                """,
                                (
                                    new_qty,
                                    current["kaspi_offer_name"],
                                    normalized_key or current["sku_key"],
                                    normalized_size or current["my_size"],
                                    existing["id"],
                                ),
                            )
                            conn.execute("DELETE FROM fact_orders_kaspi WHERE rowid = ?", (row["rid"],))
                        updated += 1
                        continue

                set_clause = ", ".join(f"{col} = ?" for col in changes.keys())
                values = list(changes.values()) + [row["rid"]]
                if args.apply:
                    conn.execute(
                        f"UPDATE {table} SET {set_clause} WHERE rowid = ?",
                        values,
                    )
                updated += 1

            stats[table] = updated

        if args.apply:
            conn.commit()
        else:
            conn.rollback()

    for table, count in stats.items():
        print(f"{table}: {count} rows updated")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
