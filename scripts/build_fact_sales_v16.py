#!/usr/bin/env python3
"""Build fact_sales_v16 from Kaspi API order entries."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
EXPORT_PATH = PROJECT_ROOT / "exports" / "fact_sales_v16_mismatch_report.md"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _load_article_map(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    if not _table_exists(conn, "dim_kaspi_article_map"):
        return {}
    cols = _table_columns(conn, "dim_kaspi_article_map")
    where_clause = ""
    if "active_flag" in cols:
        where_clause = "WHERE active_flag IS NULL OR active_flag = 1"
    rows = conn.execute(
        f"""
        SELECT store_code, kaspi_article, sku_key, sku_id
        FROM dim_kaspi_article_map
        {where_clause}
        """
    ).fetchall()
    return {(row[0], row[1]): {"sku_key": row[2], "sku_id": row[3]} for row in rows}


def build_fact_sales_v16(db_path: Path, apply: bool, run_id: str) -> dict:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_order_entries_kaspi"):
            raise RuntimeError("fact_order_entries_kaspi missing; run migrate_019_kaspi_enrichment.py")
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError("fact_orders_kaspi missing")
        if not _table_exists(conn, "fact_sales_v16"):
            raise RuntimeError("fact_sales_v16 missing; run migrate_021_fact_sales_v16.py")

        article_map = _load_article_map(conn)

        entries = conn.execute(
            """
            SELECT entry_id, order_id, store_code, offer_id, quantity, unit_price_kzt, total_price_kzt
            FROM fact_order_entries_kaspi
            """
        ).fetchall()

        order_cols = _table_columns(conn, "fact_orders_kaspi")
        select_delivery_for_seller = (
            "delivery_cost_for_seller" if "delivery_cost_for_seller" in order_cols else "NULL as delivery_cost_for_seller"
        )
        select_delivery_cost = (
            "delivery_cost" if "delivery_cost" in order_cols else "NULL as delivery_cost"
        )
        orders = conn.execute(
            f"""
            SELECT order_id, store_code, kaspi_offer_name, sku_key, sku_id,
                   {select_delivery_for_seller}, {select_delivery_cost}
            FROM fact_orders_kaspi
            """
        ).fetchall()
        orders_by_id = {(row["order_id"], row["store_code"]): row for row in orders}

        totals_by_order: dict[tuple[str, str], float] = {}
        counts_by_order: dict[tuple[str, str], int] = {}
        for row in entries:
            key = (row["order_id"], row["store_code"])
            totals_by_order[key] = totals_by_order.get(key, 0.0) + float(row["total_price_kzt"] or 0.0)
            counts_by_order[key] = counts_by_order.get(key, 0) + 1

        missing = []
        inserted = 0

        for row in entries:
            order_key = (row["order_id"], row["store_code"])
            order = orders_by_id.get(order_key)
            order_total = totals_by_order.get(order_key, 0.0)
            entry_total = float(row["total_price_kzt"] or 0.0)
            delivery_fee = 0.0
            if order is not None:
                fee = order["delivery_cost_for_seller"]
                if fee is None:
                    fee = order["delivery_cost"]
                fee = float(fee or 0.0)
                if order_total > 0:
                    delivery_fee = fee * (entry_total / order_total)
                else:
                    delivery_fee = fee
            net_rev = entry_total - delivery_fee

            sku_key = None
            sku_id = None
            map_key = (row["store_code"], row["offer_id"])
            mapping = article_map.get(map_key)
            if mapping:
                sku_key = mapping.get("sku_key")
                sku_id = mapping.get("sku_id")

            if not sku_key and order is not None and counts_by_order.get(order_key, 0) == 1:
                sku_key = order["sku_key"]
                sku_id = order["sku_id"]

            if not sku_key:
                missing.append(row["entry_id"])

            if apply:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO fact_sales_v16 (
                        entry_id, order_id, store_code, offer_id, sku_key, sku_id,
                        quantity, unit_price_kzt, total_price_kzt, delivery_fee_kzt,
                        net_rev_kzt, source, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["entry_id"],
                        row["order_id"],
                        row["store_code"],
                        row["offer_id"],
                        sku_key,
                        sku_id,
                        float(row["quantity"] or 0.0),
                        float(row["unit_price_kzt"] or 0.0),
                        entry_total,
                        round(delivery_fee, 2),
                        round(net_rev, 2),
                        "API_ENTRIES",
                        run_id,
                    ),
                )
                inserted += 1
            else:
                inserted += 1

        if apply:
            conn.commit()

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if missing:
        lines = ["# fact_sales_v16 unmapped entries", "", "Missing sku_key for entries:"]
        lines.extend([f"- {entry_id}" for entry_id in missing[:50]])
        if len(missing) > 50:
            lines.append(f"- ... ({len(missing) - 50} more)")
        EXPORT_PATH.write_text("\n".join(lines) + "\n")
    else:
        EXPORT_PATH.write_text("# fact_sales_v16 unmapped entries\n\nNone.\n")

    return {"inserted": inserted, "missing": len(missing)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fact_sales_v16 from Kaspi API entries")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true", help="Write to DB")
    parser.add_argument("--run-id", type=str, default=None)
    args = parser.parse_args()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    result = build_fact_sales_v16(args.db, apply=args.apply, run_id=run_id)
    print(f"Inserted: {result.get('inserted')}")
    print(f"Missing sku_key: {result.get('missing')}")
    print(f"Report: {EXPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
