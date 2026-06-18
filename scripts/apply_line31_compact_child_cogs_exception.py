#!/usr/bin/env python3
"""Apply the narrow owner-promoted compact-child COGS repair.

This script intentionally handles only the June 1 LINE31 strict-gate exception:
promote the copied-temp parent-unit COGS values for three compact child SKU
families into production `dim_sku.cogs_kzt`, then add the missing positive
on-delivery inventory-cost events for the named shipped orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.sales import ensure_sales_truth_views

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
REQUIRED_ENV = "AB_ALLOW_LINE31_COMPACT_CHILD_COGS_PRODUCTION_PROMOTION"
RUN_ID = "line31_compact_child_cogs_exception_20260601"
SOURCE = "OWNER_PROMOTED_PARENT_UNIT_COGS_PRODUCTION_20260601"

SKU_COGS_KZT = {
    "LINE-31-TS": 6006.76,
    "SUIT-31-LS": 5567.22,
    "SUIT-31-TS": 5567.22,
}

ON_DELIVERY_EVENTS = [
    {
        "event_date": "2026-05-28",
        "event_type": "INVENTORY_MOVE",
        "account": "INVENTORY_ON_DELIVERY_COST",
        "amount_kzt": 6006.76,
        "store_code": "ACMEWEAR",
        "sku_key": "LINE-31-TS",
        "sku_id": "LINE-31-TS_XL",
        "ref_type": "ORDER",
        "ref_id": "938256969",
        "notes": "Owner-promoted compact-child parent-unit COGS exception; not ChildSum component economics.",
        "source": SOURCE,
        "run_id": RUN_ID,
    },
    {
        "event_date": "2026-05-30",
        "event_type": "INVENTORY_MOVE",
        "account": "INVENTORY_ON_DELIVERY_COST",
        "amount_kzt": 5567.22,
        "store_code": "ACMEWEAR",
        "sku_key": "SUIT-31-LS",
        "sku_id": "SUIT-31-LS_3XL",
        "ref_type": "ORDER",
        "ref_id": "940453925",
        "notes": "Owner-promoted compact-child parent-unit COGS exception; not ChildSum component economics.",
        "source": SOURCE,
        "run_id": RUN_ID,
    },
    {
        "event_date": "2026-05-31",
        "event_type": "INVENTORY_MOVE",
        "account": "INVENTORY_ON_DELIVERY_COST",
        "amount_kzt": 5567.22,
        "store_code": "ACMEWEAR",
        "sku_key": "SUIT-31-LS",
        "sku_id": "SUIT-31-LS_XL",
        "ref_type": "ORDER",
        "ref_id": "941824782",
        "notes": "Owner-promoted compact-child parent-unit COGS exception; not ChildSum component economics.",
        "source": SOURCE,
        "run_id": RUN_ID,
    },
]


def _event_hash(event: dict[str, Any]) -> str:
    parts = [
        str(event.get("event_date") or ""),
        str(event.get("event_type") or ""),
        str(event.get("account") or ""),
        f"{float(event.get('amount_kzt') or 0.0):.4f}",
        str(event.get("store_code") or ""),
        str(event.get("sku_key") or ""),
        str(event.get("sku_id") or ""),
        str(event.get("ref_type") or ""),
        str(event.get("ref_id") or ""),
        str(event.get("source") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _fetch_dim_sku(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT sku_key, base_cost_cny, weight_kg, cogs_kzt, updated_at
        FROM dim_sku
        WHERE sku_key IN (?, ?, ?)
        ORDER BY sku_key
        """,
        tuple(sorted(SKU_COGS_KZT)),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_sales_truth(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_sales_truth_views(conn)
    rows = conn.execute(
        """
        SELECT order_id, sale_date, store_code, sku_key, sku_id, units,
               net_rev_kzt, cogs_kzt, profit_kzt, cogs_source
        FROM view_sales_line_truth
        WHERE order_id = '909054064'
           OR sku_key IN (?, ?, ?)
        ORDER BY order_id, sku_id
        """,
        tuple(sorted(SKU_COGS_KZT)),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_on_delivery(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_date, event_type, account, amount_kzt, store_code, sku_key,
               sku_id, ref_type, ref_id, notes, source, run_id, event_hash
        FROM fact_cashflow_events
        WHERE ref_id IN ('938256969', '940453925', '941824782')
          AND account = 'INVENTORY_ON_DELIVERY_COST'
        ORDER BY ref_id, event_hash
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _capture(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "dim_sku": _fetch_dim_sku(conn),
        "sales_truth": _fetch_sales_truth(conn),
        "on_delivery_events": _fetch_on_delivery(conn),
    }


def _apply(conn: sqlite3.Connection) -> None:
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    for sku_key, cogs_kzt in SKU_COGS_KZT.items():
        row = conn.execute("SELECT sku_key FROM dim_sku WHERE sku_key = ?", (sku_key,)).fetchone()
        if row is None:
            raise RuntimeError(f"dim_sku missing required sku_key: {sku_key}")
        conn.execute(
            """
            UPDATE dim_sku
            SET cogs_kzt = ?, updated_at = ?
            WHERE sku_key = ?
            """,
            (float(cogs_kzt), now, sku_key),
        )

    for event in ON_DELIVERY_EVENTS:
        event = dict(event)
        event["event_hash"] = _event_hash(event)
        conn.execute(
            """
            INSERT OR IGNORE INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key,
                sku_id, ref_type, ref_id, notes, source, run_id, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_date"],
                event["event_type"],
                event["account"],
                float(event["amount_kzt"]),
                event["store_code"],
                event["sku_key"],
                event["sku_id"],
                event["ref_type"],
                event["ref_id"],
                event["notes"],
                event["source"],
                event["run_id"],
                event["event_hash"],
            ),
        )
    ensure_sales_truth_views(conn)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.apply and os.environ.get(REQUIRED_ENV) != "1":
        raise RuntimeError(f"{REQUIRED_ENV}=1 is required with --apply")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(args.db))
    conn.row_factory = sqlite3.Row
    try:
        before = _capture(conn)
        if args.apply:
            _apply(conn)
            conn.commit()
        after = _capture(conn)
    finally:
        conn.close()

    report = {
        "db": str(args.db),
        "applied": bool(args.apply),
        "required_env": REQUIRED_ENV,
        "run_id": RUN_ID,
        "source": SOURCE,
        "sku_cogs_kzt": SKU_COGS_KZT,
        "on_delivery_ref_ids": [event["ref_id"] for event in ON_DELIVERY_EVENTS],
        "before": before,
        "after": after,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "applied": bool(args.apply), "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
