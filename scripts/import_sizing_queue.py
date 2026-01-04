#!/usr/bin/env python3
"""
Import sizing decisions from a CSV into fact_orders_kaspi (DB-first).

Expected columns (case-insensitive):
- order_id (required)
- my_size (optional)
- customer_height_cm / customer_weight_kg (optional)
- decided_by, method (optional)

Updates assigned_size + audit fields when my_size is provided.
"""
from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, date
from pathlib import Path
from typing import Any

from core.db import DEFAULT_DB_PATH, get_db
from core.paths import data_path, get_data_root


SIZE_SOURCE = "QUEUE_MANUAL"
SIZE_CONFIDENCE = "1.0"


def _normalize(value: Any) -> str:
    return "".join(str(value).strip().lower().split())


def _normalize_order_id(value: Any) -> str:
    if value is None:
        return ""
    order_id = str(value).strip()
    if order_id.endswith(".0"):
        order_id = order_id[:-2]
    return order_id


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _ensure_columns(conn) -> None:
    required = {
        "assigned_size": "TEXT",
        "size_source": "TEXT",
        "size_confidence": "TEXT",
        "customer_height_cm": "INTEGER",
        "customer_weight_kg": "INTEGER",
        "size_decided_at": "TEXT",
        "size_decided_by": "TEXT",
        "size_decision_method": "TEXT",
        "updated_at": "TEXT",
    }
    existing = {row[1] for row in conn.execute("PRAGMA table_info(fact_orders_kaspi)")}
    for col, col_type in required.items():
        if col in existing:
            continue
        conn.execute(
            f"ALTER TABLE fact_orders_kaspi ADD COLUMN {col} {col_type}"
        )


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        val = str(value).strip()
        if not val or val.lower() in ("nan", "none"):
            return None
        return int(float(val))
    except Exception:
        return None


def import_sizing_queue(
    db_path: Path,
    input_path: Path,
    decided_by: str,
    method: str,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {
        "rows": 0,
        "updated_sizes": 0,
        "updated_measurements": 0,
        "missing_orders": 0,
        "skipped_no_data": 0,
    }

    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    with open(input_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with get_db(db_path) as conn:
        if not _table_exists(conn, "fact_orders_kaspi"):
            raise RuntimeError(
                "Missing table fact_orders_kaspi. Run: python scripts/sync_kaspi_orders.py --all"
            )
        _ensure_columns(conn)

        for row in rows:
            stats["rows"] += 1
            norm_row = {_normalize(k): v for k, v in row.items()}

            order_id = _normalize_order_id(
                norm_row.get("order_id")
                or norm_row.get("orderid")
                or norm_row.get("№заказа")
                or norm_row.get("номерзаказа")
            )
            if not order_id:
                stats["skipped_no_data"] += 1
                continue

            my_size = (
                norm_row.get("my_size")
                or norm_row.get("mysize")
                or norm_row.get("size")
                or norm_row.get("assigned_size")
                or ""
            )
            my_size = str(my_size).strip()
            if my_size.lower() in ("", "nan", "none"):
                my_size = ""

            height = _parse_int(
                norm_row.get("customer_height_cm")
                or norm_row.get("height_cm")
                or norm_row.get("height")
                or norm_row.get("рост")
            )
            weight = _parse_int(
                norm_row.get("customer_weight_kg")
                or norm_row.get("weight_kg")
                or norm_row.get("weight")
                or norm_row.get("вес")
            )

            row_decided_by = (
                norm_row.get("decided_by")
                or norm_row.get("decider")
                or norm_row.get("operator")
                or decided_by
            )
            row_method = norm_row.get("method") or norm_row.get("decision_method") or method

            if not my_size and height is None and weight is None:
                stats["skipped_no_data"] += 1
                continue

            exists = conn.execute(
                "SELECT id FROM fact_orders_kaspi WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not exists:
                stats["missing_orders"] += 1
                continue

            decided_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if dry_run:
                if my_size:
                    stats["updated_sizes"] += 1
                elif height is not None or weight is not None:
                    stats["updated_measurements"] += 1
                continue

            if my_size:
                conn.execute(
                    """
                    UPDATE fact_orders_kaspi
                    SET assigned_size = ?,
                        size_source = ?,
                        size_confidence = ?,
                        customer_height_cm = COALESCE(?, customer_height_cm),
                        customer_weight_kg = COALESCE(?, customer_weight_kg),
                        size_decided_at = ?,
                        size_decided_by = ?,
                        size_decision_method = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                    """,
                    (
                        my_size,
                        SIZE_SOURCE,
                        SIZE_CONFIDENCE,
                        height,
                        weight,
                        decided_at,
                        row_decided_by,
                        row_method,
                        order_id,
                    ),
                )
                stats["updated_sizes"] += 1
            else:
                conn.execute(
                    """
                    UPDATE fact_orders_kaspi
                    SET customer_height_cm = COALESCE(?, customer_height_cm),
                        customer_weight_kg = COALESCE(?, customer_weight_kg),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = ?
                    """,
                    (height, weight, order_id),
                )
                stats["updated_measurements"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Import sizing decisions from CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--input", type=Path, required=False)
    parser.add_argument("--decided-by", type=str, default=None)
    parser.add_argument("--method", type=str, default="MANUAL_QUEUE")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    decided_by = args.decided_by or os.environ.get("USER") or "operator"
    input_path = args.input or data_path(
        "exports", f"sizing_queue_{date.today().isoformat()}.csv"
    )

    print(f"Data root: {get_data_root()}")
    print(f"DB: {args.db}")
    print(f"Input: {input_path}")
    print(f"Decided by: {decided_by}")
    print(f"Method: {args.method}")
    if args.dry_run:
        print("[DRY RUN] No DB writes")

    stats = import_sizing_queue(
        args.db,
        input_path,
        decided_by=decided_by,
        method=args.method,
        dry_run=args.dry_run,
    )

    print("\nSummary:")
    print(f"  Rows processed: {stats['rows']}")
    print(f"  Updated sizes: {stats['updated_sizes']}")
    print(f"  Updated measurements: {stats['updated_measurements']}")
    print(f"  Missing orders: {stats['missing_orders']}")
    print(f"  Skipped (no data): {stats['skipped_no_data']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
