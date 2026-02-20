#!/usr/bin/env python3
"""
Audit order size integrity vs sales_fact_v2.

Outputs CSVs to exports/:
 - orders_size_mismatch_by_updated_timestamp.csv
 - orders_size_mismatch_by_day.csv
 - orders_size_mismatch_samples.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
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


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _key(order_id: Any, store_code: Any, sku_key: Any, offer: Any) -> tuple[str, str, str, str]:
    return (
        str(order_id or "").strip(),
        str(store_code or "").strip(),
        str(sku_key or "").strip(),
        str(offer or "").strip(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit order size integrity")
    parser.add_argument("--since", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--db", default=None, help="DB path override")
    args = parser.parse_args()

    start = _parse_date(args.since)
    end = _parse_date(args.until)
    db_path = Path(args.db).expanduser() if args.db else DEFAULT_DB_PATH

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    mismatch_by_ts_path = EXPORT_DIR / "orders_size_mismatch_by_updated_timestamp.csv"
    mismatch_by_day_path = EXPORT_DIR / "orders_size_mismatch_by_day.csv"
    mismatch_samples_path = EXPORT_DIR / "orders_size_mismatch_samples.csv"

    with get_db(db_path) as conn:
        conn.row_factory = None
        synonyms = _load_size_synonyms(conn)

        sales_rows = conn.execute(
            """
            SELECT order_id, store_code, sku_key, kaspi_offer_name, my_size, quantity
            FROM sales_fact_v2
            WHERE order_date BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        sales_map: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        sales_map_short: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        sales_map_sku_id: dict[tuple[str, str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for order_id, store_code, sku_key, offer, my_size, qty in sales_rows:
            size = _norm_size(my_size, synonyms)
            if not size:
                continue
            key = _key(order_id, store_code, sku_key, offer)
            sales_map[key][size] += int(qty or 0)
            short_key = (str(order_id or "").strip(), str(store_code or "").strip())
            sales_map_short[short_key][size] += int(qty or 0)
            # sku_id-based lookup is built separately below

        order_rows = conn.execute(
            """
            SELECT id, order_id, store_code, sku_key, sku_id, kaspi_offer_name,
                   assigned_size, my_size, updated_at, planned_shipment_date, created_at
            FROM fact_orders_kaspi
            WHERE date(COALESCE(planned_shipment_date, created_at)) BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        sales_rows_with_sku_id = conn.execute(
            """
            SELECT order_id, store_code, sku_id, my_size, quantity
            FROM sales_fact_v2
            WHERE order_date BETWEEN ? AND ?
              AND sku_id IS NOT NULL
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        for order_id, store_code, sku_id, my_size, qty in sales_rows_with_sku_id:
            size = _norm_size(my_size, synonyms)
            if not size:
                continue
            key = (str(order_id or "").strip(), str(store_code or "").strip(), str(sku_id or "").strip())
            sales_map_sku_id[key][size] += int(qty or 0)

    mismatches: list[dict[str, Any]] = []
    mismatch_by_ts: dict[str, int] = defaultdict(int)
    by_day_store: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for (
        row_id,
        order_id,
        store_code,
        sku_key,
        sku_id,
        offer,
        assigned_size,
        my_size,
        updated_at,
        planned_shipment_date,
        created_at,
    ) in order_rows:
        key = _key(order_id, store_code, sku_key, offer)
        size = _norm_size(assigned_size or my_size, synonyms)
        if size:
            day = str(planned_shipment_date or created_at or "")[:10]
            if day:
                by_day_store[(day, str(store_code or ""))][size] += 1

        sizes_from_sales = None
        if sku_id:
            sku_id_key = (str(order_id or "").strip(), str(store_code or "").strip(), str(sku_id or "").strip())
            sizes_from_sales = sales_map_sku_id.get(sku_id_key)
        if not sizes_from_sales:
            sizes_from_sales = sales_map.get(key)
        if not sizes_from_sales:
            short_key = (str(order_id or "").strip(), str(store_code or "").strip())
            sizes_from_sales = sales_map_short.get(short_key)
        if not sizes_from_sales:
            continue
        if not size:
            continue
        if size in sizes_from_sales:
            continue

        updated = str(updated_at or "")
        updated_min = updated.replace("T", " ")[:16] if updated else "unknown"
        mismatch_by_ts[updated_min] += 1
        mismatches.append(
            {
                "id": row_id,
                "order_id": order_id,
                "store_code": store_code,
                "sku_key": sku_key,
                "kaspi_offer_name": offer,
                "assigned_size": assigned_size,
                "my_size": my_size,
                "sales_sizes": "|".join(sorted(sizes_from_sales.keys())),
                "updated_at": updated_at,
                "planned_shipment_date": planned_shipment_date,
                "created_at": created_at,
            }
        )

    # Write mismatch by updated timestamp
    with mismatch_by_ts_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["updated_minute", "mismatch_count"])
        writer.writeheader()
        for minute, count in sorted(mismatch_by_ts.items()):
            writer.writerow({"updated_minute": minute, "mismatch_count": count})

    # Write mismatch by day (top size share)
    with mismatch_by_day_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["date", "store_code", "total_orders", "top_size", "top_count", "top_share"],
        )
        writer.writeheader()
        for (day, store), counts in sorted(by_day_store.items()):
            total = sum(counts.values())
            if total <= 0:
                continue
            top_size, top_count = max(counts.items(), key=lambda item: item[1])
            writer.writerow(
                {
                    "date": day,
                    "store_code": store,
                    "total_orders": total,
                    "top_size": top_size,
                    "top_count": top_count,
                    "top_share": round(top_count / total, 3),
                }
            )

    # Write mismatch samples
    with mismatch_samples_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(mismatches[0].keys()) if mismatches else [])
        if mismatches:
            writer.writeheader()
            writer.writerows(mismatches[:500])

    print(f"Wrote {mismatch_by_ts_path}")
    print(f"Wrote {mismatch_by_day_path}")
    print(f"Wrote {mismatch_samples_path}")
    print(f"Total mismatches: {len(mismatches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
