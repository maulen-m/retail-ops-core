#!/usr/bin/env python3
"""
Migration 017: Canonicalize LINE52 numeric size tokens (42 -> S).

Updates dim_sku_size and all dependent tables to replace:
  CL_OC_MEN_LINE52_BLACK_42 -> CL_OC_MEN_LINE52_BLACK_S
  my_size 42 -> S

Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"

SIZE_MAP = {
    "42": "S",
}

SIZE_ORDER = {
    "XS": 0,
    "S": 1,
    "M": 2,
    "L": 3,
    "XL": 4,
    "2XL": 5,
    "3XL": 6,
    "4XL": 7,
    "5XL": 8,
}

TABLES_TO_UPDATE = [
    "fact_sales",
    "sales_fact_v2",
    "fact_sales_daily_size",
    "fact_inventory_snapshot_size",
    "fact_po_lines",
    "po_line",
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _table_has_column(conn: sqlite3.Connection, name: str, col: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({name})").fetchall()
    return any(r[1] == col for r in rows)


def _update_table(
    conn: sqlite3.Connection,
    table: str,
    old_id: str,
    new_id: str,
    old_size: str,
    new_size: str,
    sku_key: str,
) -> None:
    if not _table_exists(conn, table):
        return
    if table == "fact_sales_daily_size":
        _merge_fact_sales_daily_size(conn, old_id, new_id, new_size)
        return
    if table == "fact_inventory_snapshot_size":
        _merge_fact_inventory_snapshot_size(conn, old_id, new_id, new_size)
        return
    has_sku_id = _table_has_column(conn, table, "sku_id")
    has_my_size = _table_has_column(conn, table, "my_size")
    has_sku_key = _table_has_column(conn, table, "sku_key")

    if has_sku_id and has_my_size:
        conn.execute(
            f"UPDATE {table} SET sku_id = ?, my_size = ? WHERE sku_id = ?",
            (new_id, new_size, old_id),
        )
    elif has_sku_id:
        conn.execute(
            f"UPDATE {table} SET sku_id = ? WHERE sku_id = ?",
            (new_id, old_id),
        )
    elif has_my_size and has_sku_key:
        conn.execute(
            f"UPDATE {table} SET my_size = ? WHERE sku_key = ? AND my_size = ?",
            (new_size, sku_key, old_size),
        )


def _merge_fact_sales_daily_size(
    conn: sqlite3.Connection,
    old_id: str,
    new_id: str,
    new_size: str,
) -> None:
    rows = conn.execute(
        """
        SELECT sale_date, store_code, units, revenue, cogs, profit
        FROM fact_sales_daily_size
        WHERE sku_id = ?
        """,
        (old_id,),
    ).fetchall()
    for sale_date, store_code, units, revenue, cogs, profit in rows:
        existing = conn.execute(
            """
            SELECT units, revenue, cogs, profit
            FROM fact_sales_daily_size
            WHERE sku_id = ? AND sale_date = ? AND store_code = ?
            """,
            (new_id, sale_date, store_code),
        ).fetchone()
        if existing:
            new_units = (existing[0] or 0) + (units or 0)
            new_rev = (existing[1] or 0) + (revenue or 0)
            new_cogs = (existing[2] or 0) + (cogs or 0)
            new_profit = (existing[3] or 0) + (profit or 0)
            conn.execute(
                """
                UPDATE fact_sales_daily_size
                SET units = ?, revenue = ?, cogs = ?, profit = ?
                WHERE sku_id = ? AND sale_date = ? AND store_code = ?
                """,
                (new_units, new_rev, new_cogs, new_profit, new_id, sale_date, store_code),
            )
            conn.execute(
                "DELETE FROM fact_sales_daily_size WHERE sku_id = ? AND sale_date = ? AND store_code = ?",
                (old_id, sale_date, store_code),
            )
        else:
            conn.execute(
                """
                UPDATE fact_sales_daily_size
                SET sku_id = ?, my_size = ?
                WHERE sku_id = ? AND sale_date = ? AND store_code = ?
                """,
                (new_id, new_size, old_id, sale_date, store_code),
            )


def _merge_fact_inventory_snapshot_size(
    conn: sqlite3.Connection,
    old_id: str,
    new_id: str,
    new_size: str,
) -> None:
    rows = conn.execute(
        """
        SELECT snapshot_date, current_stock, inbound_stock
        FROM fact_inventory_snapshot_size
        WHERE sku_id = ?
        """,
        (old_id,),
    ).fetchall()
    for snapshot_date, current_stock, inbound_stock in rows:
        existing = conn.execute(
            """
            SELECT current_stock, inbound_stock
            FROM fact_inventory_snapshot_size
            WHERE sku_id = ? AND snapshot_date = ?
            """,
            (new_id, snapshot_date),
        ).fetchone()
        if existing:
            new_current = (existing[0] or 0) + (current_stock or 0)
            new_inbound = (existing[1] or 0) + (inbound_stock or 0)
            conn.execute(
                """
                UPDATE fact_inventory_snapshot_size
                SET current_stock = ?, inbound_stock = ?
                WHERE sku_id = ? AND snapshot_date = ?
                """,
                (new_current, new_inbound, new_id, snapshot_date),
            )
            conn.execute(
                "DELETE FROM fact_inventory_snapshot_size WHERE sku_id = ? AND snapshot_date = ?",
                (old_id, snapshot_date),
            )
        else:
            conn.execute(
                """
                UPDATE fact_inventory_snapshot_size
                SET sku_id = ?, my_size = ?
                WHERE sku_id = ? AND snapshot_date = ?
                """,
                (new_id, new_size, old_id, snapshot_date),
            )


def migrate(db_path: Path, sku_key: str) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "dim_sku_size"):
            print("dim_sku_size missing; nothing to migrate.")
            return

        rows = conn.execute(
            """
            SELECT sku_id, my_size
            FROM dim_sku_size
            WHERE sku_key = ?
              AND my_size IN ({placeholders})
            """.format(placeholders=",".join(["?"] * len(SIZE_MAP))),
            [sku_key, *SIZE_MAP.keys()],
        ).fetchall()

        if not rows:
            print("No LINE52 numeric size rows found; nothing to migrate.")
            return

        for sku_id, my_size in rows:
            canonical = SIZE_MAP.get(my_size)
            if not canonical:
                continue
            new_id = f"{sku_key}_{canonical}"

            # Update dependent tables
            for table in TABLES_TO_UPDATE:
                _update_table(
                    conn,
                    table,
                    sku_id,
                    new_id,
                    my_size,
                    canonical,
                    sku_key,
                )

            # Update dim_sku_size
            existing = conn.execute(
                "SELECT 1 FROM dim_sku_size WHERE sku_id = ?",
                (new_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "DELETE FROM dim_sku_size WHERE sku_id = ?",
                    (sku_id,),
                )
            else:
                size_order = SIZE_ORDER.get(canonical)
                if size_order is None:
                    conn.execute(
                        "UPDATE dim_sku_size SET sku_id = ?, my_size = ? WHERE sku_id = ?",
                        (new_id, canonical, sku_id),
                    )
                else:
                    conn.execute(
                        "UPDATE dim_sku_size SET sku_id = ?, my_size = ?, size_order = ? WHERE sku_id = ?",
                        (new_id, canonical, size_order, sku_id),
                    )

        conn.commit()
        print("Migration complete: LINE52 numeric sizes canonicalized.")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonicalize LINE52 size 42 -> S")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument(
        "--sku-key",
        type=str,
        default="CL_OC_MEN_LINE52_BLACK",
        help="SKU key to canonicalize (default: CL_OC_MEN_LINE52_BLACK)",
    )
    args = parser.parse_args()

    migrate(args.db, args.sku_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
