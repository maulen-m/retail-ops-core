#!/usr/bin/env python3
"""
Fix corrupted assigned_size values in fact_orders_kaspi from sales_fact_v2.

Default is dry-run. Use --apply with ENABLE_ORDER_WRITE=1 to apply updates.
Writes a CSV change log to exports/.
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH
from core.utils.sku_normalize import normalize_size

EXPORT_DIR = PROJECT_ROOT / "exports"


def _load_size_synonyms(conn) -> dict[str, str]:
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_size_synonyms'"
    ).fetchone()
    if not table:
        return {}
    rows = conn.execute("SELECT alias, canonical_size FROM dim_size_synonyms").fetchall()
    synonyms: dict[str, str] = {}
    for alias, canonical in rows:
        if not alias or not canonical:
            continue
        key = str(alias).upper().replace(" ", "").replace("-", "")
        synonyms[key] = str(canonical).strip()
    return synonyms


def _norm_size(value: Any, synonyms: dict[str, str]) -> str:
    return normalize_size(str(value or "").strip(), synonyms=synonyms) or ""


def _key(order_id: Any, store_code: Any, sku_key: Any, offer: Any) -> tuple[str, str, str, str]:
    return (
        str(order_id or "").strip(),
        str(store_code or "").strip(),
        str(sku_key or "").strip(),
        str(offer or "").strip(),
    )


def _parse_ts(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix assigned_size in fact_orders_kaspi")
    parser.add_argument("--window-start", required=True, help="Window start (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--window-end", required=True, help="Window end (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument("--db", default=None, help="DB path override")
    args = parser.parse_args()

    apply = args.apply
    if apply and os.environ.get("ENABLE_ORDER_WRITE") != "1":
        print("ERROR: ENABLE_ORDER_WRITE=1 is required to apply changes.")
        return 1

    start_ts = _parse_ts(args.window_start)
    end_ts = _parse_ts(args.window_end)
    db_path = Path(args.db).expanduser() if args.db else DEFAULT_DB_PATH

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_start = start_ts.strftime("%Y%m%d_%H%M%S")
    safe_end = end_ts.strftime("%Y%m%d_%H%M%S")
    out_path = EXPORT_DIR / f"orders_size_fix_{safe_start}_{safe_end}.csv"

    updates: list[dict[str, Any]] = []

    with get_db(db_path) as conn:
        synonyms = _load_size_synonyms(conn)

        sales_rows = conn.execute(
            """
            SELECT order_id, store_code, sku_key, kaspi_offer_name, my_size, quantity
            FROM sales_fact_v2
            """
        ).fetchall()

        sales_map: dict[tuple[str, str, str, str], dict[str, int]] = {}
        sales_map_short: dict[tuple[str, str], dict[str, int]] = {}
        sales_map_sku_id: dict[tuple[str, str, str], dict[str, int]] = {}
        for order_id, store_code, sku_key, offer, my_size, qty in sales_rows:
            size = _norm_size(my_size, synonyms)
            if not size:
                continue
            key = _key(order_id, store_code, sku_key, offer)
            sales_map.setdefault(key, {})
            sales_map[key][size] = sales_map[key].get(size, 0) + int(qty or 0)
            short_key = (str(order_id or "").strip(), str(store_code or "").strip())
            sales_map_short.setdefault(short_key, {})
            sales_map_short[short_key][size] = sales_map_short[short_key].get(size, 0) + int(qty or 0)

        rows = conn.execute(
            """
            SELECT id, order_id, store_code, sku_key, sku_id, kaspi_offer_name,
                   assigned_size, my_size, size_source, size_confidence, updated_at
            FROM fact_orders_kaspi
            WHERE updated_at BETWEEN ? AND ?
            """,
            (start_ts.isoformat(sep=" "), end_ts.isoformat(sep=" ")),
        ).fetchall()

        sales_rows_with_sku_id = conn.execute(
            """
            SELECT order_id, store_code, sku_id, my_size, quantity
            FROM sales_fact_v2
            WHERE sku_id IS NOT NULL
            """,
            ()
        ).fetchall()
        for order_id, store_code, sku_id, my_size, qty in sales_rows_with_sku_id:
            size = _norm_size(my_size, synonyms)
            if not size:
                continue
            key = (str(order_id or "").strip(), str(store_code or "").strip(), str(sku_id or "").strip())
            sales_map_sku_id.setdefault(key, {})
            sales_map_sku_id[key][size] = sales_map_sku_id[key].get(size, 0) + int(qty or 0)

        for (
            row_id,
            order_id,
            store_code,
            sku_key,
            sku_id,
            offer,
            assigned_size,
            my_size,
            size_source,
            size_confidence,
            updated_at,
        ) in rows:
            key = _key(order_id, store_code, sku_key, offer)
            sizes = None
            if sku_id:
                sku_id_key = (str(order_id or "").strip(), str(store_code or "").strip(), str(sku_id or "").strip())
                sizes = sales_map_sku_id.get(sku_id_key)
            if not sizes:
                sizes = sales_map.get(key)
            if not sizes:
                short_key = (str(order_id or "").strip(), str(store_code or "").strip())
                candidate = sales_map_short.get(short_key)
                if candidate and len(candidate) == 1:
                    sizes = candidate
            if not sizes:
                continue
            if len(sizes) != 1:
                continue
            new_size = next(iter(sizes.keys()))
            current = _norm_size(assigned_size or my_size, synonyms)
            if not new_size or current == new_size:
                continue
            updates.append(
                {
                    "id": row_id,
                    "order_id": order_id,
                    "store_code": store_code,
                    "sku_key": sku_key,
                    "kaspi_offer_name": offer,
                    "assigned_size_old": assigned_size,
                    "assigned_size_new": new_size,
                    "size_source_old": size_source,
                    "size_confidence_old": size_confidence,
                    "updated_at": updated_at,
                }
            )

        if apply and updates:
            for row in updates:
                conn.execute(
                    """
                    UPDATE fact_orders_kaspi
                    SET assigned_size = ?,
                        size_source = ?,
                        size_confidence = ?
                    WHERE id = ?
                    """,
                    (
                        row["assigned_size_new"],
                        "FIXED_FROM_SALES_V2",
                        "HIGH",
                        row["id"],
                    ),
                )

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        if updates:
            writer = csv.DictWriter(fh, fieldnames=list(updates[0].keys()))
            writer.writeheader()
            writer.writerows(updates)

    print(f"Wrote {out_path}")
    print(f"Total updates: {len(updates)}")
    if apply:
        print("Applied changes.")
    else:
        print("Dry-run only (no DB writes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
