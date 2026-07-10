#!/usr/bin/env python3
"""Validate ON_DELIVERY inventory freeze balances against latest order statuses."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_order_stage import (  # noqa: E402
    StageCode,
    classify_kaspi_stage_from_db_row,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def validate_on_delivery_freeze(
    *,
    db_path: Path = DEFAULT_DB,
    since: date | None = None,
    until: date | None = None,
    tolerance_kzt: float = 1.0,
    lookback_days: int = 14,
) -> list[str]:
    errors: list[str] = []
    if not db_path.exists():
        return [f"db not found: {db_path}"]

    as_of = until or date.today()
    start = since or (as_of - timedelta(days=max(1, int(lookback_days)) - 1))

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_orders_kaspi"):
            return ["fact_orders_kaspi missing"]
        if not _table_exists(conn, "fact_cashflow_events"):
            return ["fact_cashflow_events missing"]

        order_cols = _table_columns(conn, "fact_orders_kaspi")
        if "order_id" not in order_cols:
            return ["fact_orders_kaspi.order_id missing"]

        date_expr = "status_updated_at"
        for candidate in ("status_updated_at", "updated_at", "created_at", "order_date"):
            if candidate in order_cols:
                date_expr = candidate
                break
        if "internal_status" not in order_cols and "status" not in order_cols:
            return ["fact_orders_kaspi status column missing (internal_status/status)"]

        has_sku_cols = "sku_key" in order_cols or "sku_id" in order_cols
        if has_sku_cols:
            # `sku_key='CL'` is a known placeholder from unresolved offer mapping.
            # Freeze checks should only enforce balances for deterministically identified rows.
            sku_expr = (
                "CASE WHEN ("
                "(COALESCE(TRIM(sku_key), '') <> '' AND UPPER(TRIM(sku_key)) NOT IN ('CL', 'UNKNOWN')) "
                "OR (COALESCE(TRIM(sku_key), '') = '' "
                "AND COALESCE(TRIM(sku_id), '') <> '' "
                "AND UPPER(TRIM(sku_id)) NOT IN ('CL', 'UNKNOWN'))"
                ") THEN 1 ELSE 0 END"
            )
        else:
            sku_expr = "1"
        order_rows = conn.execute(
            f"""
            SELECT *,
                   {sku_expr} AS has_sku_identity
            FROM fact_orders_kaspi
            WHERE date(COALESCE({date_expr}, '1970-01-01')) BETWEEN ? AND ?
              AND COALESCE(TRIM(order_id), '') <> ''
            """,
            (start.isoformat(), as_of.isoformat()),
        ).fetchall()

        stage_by_order: dict[str, StageCode] = {}
        sku_identity_by_order: dict[str, bool] = {}
        for row in order_rows:
            order_id = str(row["order_id"])
            stage_by_order[order_id] = classify_kaspi_stage_from_db_row(dict(row))
            sku_identity_by_order[order_id] = bool(int(row["has_sku_identity"] or 0))

        balances = conn.execute(
            """
            SELECT ref_id AS order_id, SUM(amount_kzt) AS balance_kzt
            FROM fact_cashflow_events
            WHERE account = 'INVENTORY_ON_DELIVERY_COST'
              AND ref_type = 'ORDER'
              AND date(event_date) <= ?
            GROUP BY ref_id
            """,
            (as_of.isoformat(),),
        ).fetchall()
        on_delivery_balance = {
            str(row["order_id"]): float(row["balance_kzt"] or 0.0)
            for row in balances
            if row["order_id"] is not None
        }

        # Only a confirmed in-delivery stage proves that a positive frozen
        # balance must exist. CANCELLING/RETURN_REQUESTED may occur before
        # handover; if they already have a frozen balance it must remain, but
        # this validator must not manufacture a missing-balance requirement.
        frozen_stages = {StageCode.IN_DELIVERY}
        settled_stages = {
            StageCode.ISSUED_COMPLETED,
            StageCode.CANCELLED,
            StageCode.RETURNED,
        }

        for order_id, stage in stage_by_order.items():
            balance = float(on_delivery_balance.get(order_id, 0.0))
            has_identity = sku_identity_by_order.get(order_id, True)
            if stage in frozen_stages and has_identity and balance <= tolerance_kzt:
                errors.append(
                    f"{order_id}: stage={stage.value} has missing INVENTORY_ON_DELIVERY_COST balance (balance={balance:.2f})"
                )
            if stage in settled_stages and has_identity and abs(balance) > tolerance_kzt:
                errors.append(
                    f"{order_id}: stage={stage.value} must settle INVENTORY_ON_DELIVERY_COST to ~0 (balance={balance:.2f})"
                )
    finally:
        conn.close()
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ON_DELIVERY inventory freeze consistency")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--since", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--until", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--tolerance-kzt", type=float, default=1.0)
    parser.add_argument("--lookback-days", type=int, default=14)
    args = parser.parse_args()

    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None
    errors = validate_on_delivery_freeze(
        db_path=args.db,
        since=since,
        until=until,
        tolerance_kzt=args.tolerance_kzt,
        lookback_days=args.lookback_days,
    )
    if errors:
        print("ON_DELIVERY_FREEZE FAILURES:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("OK: on-delivery freeze validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
