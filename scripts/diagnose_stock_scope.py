#!/usr/bin/env python3
"""
Diagnostics for stock scope, SKU_ID aliasing, and inbound source overlap.

Outputs CSVs to exports/debug_stock_scope_*.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import normalize_sku_id


EXPORT_DIR = PROJECT_ROOT / "exports"


def _write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)


def _parse_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose inventory scope and SKU_ID aliasing")
    parser.add_argument("--as-of-date", default="2026-01-13", help="Ledger as-of date YYYY-MM-DD")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    args = parser.parse_args()

    as_of_date = _parse_date(args.as_of_date)

    with get_db(args.db) as conn:
        # A) Snapshot rows by store_code if present
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(fact_inventory_snapshot_size)").fetchall()]
        snapshot_store_path = EXPORT_DIR / "debug_stock_scope_snapshot_store.csv"
        if "store_code" in cols:
            rows = conn.execute(
                """
                SELECT snapshot_date, sku_key, my_size, store_code, SUM(current_stock) as current_stock
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date = ?
                GROUP BY snapshot_date, sku_key, my_size, store_code
                ORDER BY sku_key, my_size, store_code
                """,
                (as_of_date,),
            ).fetchall()
            _write_csv(
                snapshot_store_path,
                ["snapshot_date", "sku_key", "my_size", "store_code", "current_stock"],
                [[r["snapshot_date"], r["sku_key"], r["my_size"], r["store_code"], r["current_stock"]] for r in rows],
            )
        else:
            _write_csv(
                snapshot_store_path,
                ["note"],
                [["fact_inventory_snapshot_size has no store_code column"]],
            )

        # B) Ledger balances by store_code
        ledger_path = EXPORT_DIR / "debug_stock_scope_ledger_store_2026-01-13.csv"
        rows = conn.execute(
            """
            SELECT sku_key, sku_id, my_size, store_code, SUM(qty_change) as balance
            FROM stock_ledger
            WHERE event_date <= ?
            GROUP BY sku_key, sku_id, my_size, store_code
            ORDER BY sku_key, sku_id, my_size, store_code
            """,
            (as_of_date,),
        ).fetchall()
        _write_csv(
            ledger_path,
            ["sku_key", "sku_id", "my_size", "store_code", "balance"],
            [[r["sku_key"], r["sku_id"], r["my_size"], r["store_code"], r["balance"]] for r in rows],
        )

        # C) SKU_ID variants for LINE52/LINE51
        variants_path = EXPORT_DIR / "debug_stock_scope_sku_id_variants.csv"
        rows = conn.execute(
            """
            SELECT sku_key, sku_id, COUNT(*) as cnt
            FROM dim_sku_size
            WHERE sku_key IN ('CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE51_WHITE')
            GROUP BY sku_key, sku_id
            ORDER BY sku_key, sku_id
            """
        ).fetchall()
        variant_rows = []
        for r in rows:
            normalized = normalize_sku_id(r["sku_id"], r["sku_key"])
            variant_rows.append([r["sku_key"], r["sku_id"], normalized, r["cnt"]])
        _write_csv(
            variants_path,
            ["sku_key", "raw_sku_id", "normalized_sku_id", "count"],
            variant_rows,
        )

        # D) Arrivals/inbound sources
        inbound_path = EXPORT_DIR / "debug_stock_scope_inbound_sources.csv"
        rows_po = conn.execute(
            """
            SELECT 'po_line' as source, pl.po_id, pl.sku_id, pl.sku_key, pl.my_size,
                   SUM(pl.order_qty - pl.received_qty) as units
            FROM po_line pl
            JOIN po_header ph ON ph.po_id = pl.po_id
            WHERE pl.status IN ('PENDING', 'PARTIAL', 'IN_TRANSIT')
              AND ph.status NOT IN ('CLOSED', 'CANCELLED')
            GROUP BY pl.po_id, pl.sku_id, pl.sku_key, pl.my_size
            """
        ).fetchall()
        rows_fact = conn.execute(
            """
            SELECT 'fact_po_lines' as source, po_id, sku_id, sku_key, my_size,
                   SUM(order_quantity - received_qty) as units
            FROM fact_po_lines
            WHERE (order_quantity - received_qty) > 0
              AND status NOT IN ('ARRIVED', 'CLOSED', 'CANCELLED', 'RECEIVED')
            GROUP BY po_id, sku_id, sku_key, my_size
            """
        ).fetchall()
        inbound_rows = [
            [r["source"], r["po_id"], r["sku_id"], r["sku_key"], r["my_size"], r["units"]]
            for r in list(rows_po) + list(rows_fact)
        ]
        _write_csv(
            inbound_path,
            ["source", "po_id", "sku_id", "sku_key", "my_size", "units"],
            inbound_rows,
        )

        # D2) Overlap detection by po_id + sku_id + size
        overlap_path = EXPORT_DIR / "debug_stock_scope_inbound_overlap.csv"
        overlap = conn.execute(
            """
            SELECT pl.po_id, pl.sku_id, pl.sku_key, pl.my_size
            FROM po_line pl
            JOIN fact_po_lines f
              ON f.po_id = pl.po_id
             AND f.sku_id = pl.sku_id
             AND f.my_size = pl.my_size
            WHERE pl.status IN ('PENDING', 'PARTIAL', 'IN_TRANSIT')
              AND (f.order_quantity - f.received_qty) > 0
            GROUP BY pl.po_id, pl.sku_id, pl.sku_key, pl.my_size
            ORDER BY pl.po_id, pl.sku_id, pl.my_size
            """
        ).fetchall()
        _write_csv(
            overlap_path,
            ["po_id", "sku_id", "sku_key", "my_size"],
            [[r["po_id"], r["sku_id"], r["sku_key"], r["my_size"]] for r in overlap],
        )

    print("Diagnostics written:")
    print(f"  {snapshot_store_path}")
    print(f"  {ledger_path}")
    print(f"  {variants_path}")
    print(f"  {inbound_path}")
    print(f"  {overlap_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
