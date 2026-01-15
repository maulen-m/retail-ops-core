#!/usr/bin/env python3
"""
Reconcile stock_ledger balances to a snapshot date.

Creates ADJUSTMENT events to align ledger balances with
fact_inventory_snapshot_size as-of the snapshot date.

Idempotent per snapshot date via reference_id.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.db import get_db, DEFAULT_DB_PATH


def _parse_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").date().isoformat()


def _load_snapshot(conn, snapshot_date: str) -> dict[str, dict]:
    rows = conn.execute(
        """
        SELECT sku_id, sku_key, my_size, current_stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        """,
        (snapshot_date,),
    ).fetchall()
    return {row["sku_id"]: dict(row) for row in rows}


def _load_ledger_balances(conn, snapshot_date: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT sku_id, SUM(qty_change) AS balance
        FROM stock_ledger
        WHERE event_date <= ?
        GROUP BY sku_id
        """,
        (snapshot_date,),
    ).fetchall()
    return {row["sku_id"]: int(row["balance"] or 0) for row in rows}


def _load_existing_adjustments(conn, snapshot_date: str, ref_id: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT sku_id
        FROM stock_ledger
        WHERE event_date = ?
          AND event_type = 'ADJUSTMENT'
          AND reference_id = ?
        """,
        (snapshot_date, ref_id),
    ).fetchall()
    return {row["sku_id"] for row in rows}


def _insert_adjustment(conn, snapshot_date: str, row: dict, diff: int, ref_id: str) -> None:
    conn.execute(
        """
        INSERT INTO stock_ledger (
            event_date, event_type, sku_key, sku_id, my_size, store_code,
            qty_change, running_balance, reference_id, reference_type,
            kaspi_offer_name, notes, input_source, created_by
        ) VALUES (?, 'ADJUSTMENT', ?, ?, ?, 'UNIVERSAL', ?, NULL, ?, 'ADJUSTMENT', NULL, ?, 'SYSTEM', 'system')
        """,
        (
            snapshot_date,
            row["sku_key"],
            row["sku_id"],
            row["my_size"],
            diff,
            ref_id,
            f"Reconcile ledger to snapshot {snapshot_date}",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile stock_ledger to snapshot date")
    parser.add_argument("--snapshot-date", required=True, help="Snapshot date YYYY-MM-DD")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="DB path")
    parser.add_argument("--apply", action="store_true", help="Apply adjustments (default: dry-run)")
    args = parser.parse_args()

    snapshot_date = _parse_date(args.snapshot_date)
    ref_id = f"SNAPSHOT_RECON_{snapshot_date}"

    with get_db(args.db) as conn:
        snapshot = _load_snapshot(conn, snapshot_date)
        if not snapshot:
            raise SystemExit(f"No snapshot rows found for {snapshot_date}")

        balances = _load_ledger_balances(conn, snapshot_date)
        existing = _load_existing_adjustments(conn, snapshot_date, ref_id)

        stats = defaultdict(int)

        # Align SKUs present in snapshot
        for sku_id, snap in snapshot.items():
            if sku_id in existing:
                stats["skipped_existing"] += 1
                continue
            target = int(snap.get("current_stock") or 0)
            balance = int(balances.get(sku_id, 0))
            diff = target - balance
            if diff == 0:
                stats["no_change"] += 1
                continue
            stats["adjustments"] += 1
            stats["units"] += diff
            if args.apply:
                _insert_adjustment(conn, snapshot_date, snap, diff, ref_id)

        # For SKUs missing from snapshot but negative in ledger, clamp to 0
        for sku_id, balance in balances.items():
            if sku_id in snapshot or sku_id in existing:
                continue
            if balance >= 0:
                continue
            stats["missing_snapshot_negatives"] += 1
            stats["adjustments"] += 1
            stats["units"] += -balance
            if args.apply:
                row = {"sku_id": sku_id, "sku_key": None, "my_size": None}
                # Try to resolve sku_key/my_size from dim_sku_size for auditability
                resolved = conn.execute(
                    "SELECT sku_key, my_size FROM dim_sku_size WHERE sku_id = ?",
                    (sku_id,),
                ).fetchone()
                if resolved:
                    row["sku_key"] = resolved["sku_key"]
                    row["my_size"] = resolved["my_size"]
                else:
                    row["sku_key"] = sku_id.rsplit("_", 1)[0] if "_" in sku_id else sku_id
                    row["my_size"] = sku_id.rsplit("_", 1)[1] if "_" in sku_id else "UNKNOWN"
                _insert_adjustment(conn, snapshot_date, row, -balance, ref_id)

        if args.apply:
            conn.commit()
        else:
            conn.rollback()

    print(f"Snapshot: {snapshot_date}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Adjustments: {stats['adjustments']}")
    print(f"Total units adjusted: {stats['units']}")
    print(f"Skipped existing: {stats['skipped_existing']}")
    print(f"No change: {stats['no_change']}")
    print(f"Missing snapshot negatives: {stats['missing_snapshot_negatives']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
