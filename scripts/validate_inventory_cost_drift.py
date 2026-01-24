#!/usr/bin/env python3
"""
Validate inventory cost drift between cashflow ledger and snapshots.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.business_params import get_fx_rates
from core.calc.economics import calc_cogs

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _load_dim_sku_costs(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "dim_sku"):
        return {}
    rows = conn.execute(
        "SELECT sku_key, cogs_kzt, base_cost_cny, weight_kg FROM dim_sku"
    ).fetchall()
    return {
        row[0]: {
            "cogs_kzt": row[1] or 0.0,
            "base_cost_cny": row[2] or 0.0,
            "weight_kg": row[3] or 0.0,
        }
        for row in rows
    }


def _compute_inventory_cost(conn: sqlite3.Connection, snapshot_date: str) -> float:
    rows = conn.execute(
        """
        SELECT sku_key, SUM(current_stock) as stock
        FROM fact_inventory_snapshot_size
        WHERE snapshot_date = ?
        GROUP BY sku_key
        """,
        (snapshot_date,),
    ).fetchall()

    fx_rates = get_fx_rates(snapshot_date, db_path=DEFAULT_DB)
    dim_costs = _load_dim_sku_costs(conn)
    total = 0.0
    for sku_key, stock in rows:
        if stock is None or stock <= 0:
            continue
        meta = dim_costs.get(sku_key, {})
        cogs_unit = meta.get("cogs_kzt") or 0.0
        if cogs_unit <= 0:
            base_cost = meta.get("base_cost_cny", 0.0)
            weight = meta.get("weight_kg", 0.0)
            cogs_unit = calc_cogs(
                base_cost,
                weight,
                cny_kzt=fx_rates.cny_kzt,
                volumetric_factor=fx_rates.dlv_rate_usd_kg,
                freight_rate=fx_rates.usd_kzt,
            )
        total += float(stock) * cogs_unit
    return round(total, 2)


def validate_drift(db_path: Path, as_of: str | None, tolerance_pct: float, tolerance_kzt: float) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_cashflow_daily"):
            print("SKIP: fact_cashflow_daily missing")
            return 0
        if not _table_exists(conn, "fact_inventory_snapshot_size"):
            print("SKIP: inventory snapshots missing")
            return 0

        max_cashflow = conn.execute("SELECT MAX(date) as max_date FROM fact_cashflow_daily").fetchone()
        max_cashflow_date = max_cashflow["max_date"] if max_cashflow and max_cashflow["max_date"] else None
        if not max_cashflow_date:
            print("SKIP: no cashflow daily rows")
            return 0

        if as_of:
            snapshot_row = conn.execute(
                "SELECT MAX(snapshot_date) as snap_date FROM fact_inventory_snapshot_size WHERE snapshot_date <= ?",
                (as_of,),
            ).fetchone()
        else:
            snapshot_row = conn.execute(
                """
                SELECT MAX(snapshot_date) as snap_date
                FROM fact_inventory_snapshot_size
                WHERE snapshot_date <= ?
                """,
                (max_cashflow_date,),
            ).fetchone()
        snapshot_date = snapshot_row["snap_date"] if snapshot_row and snapshot_row["snap_date"] else None
        if not snapshot_date:
            print("SKIP: no snapshot available to compare")
            return 0

        cashflow_row = conn.execute(
            "SELECT inventory_cost_close FROM fact_cashflow_daily WHERE date = ?",
            (snapshot_date,),
        ).fetchone()
        if not cashflow_row:
            print(f"SKIP: cashflow daily missing for {snapshot_date}")
            return 0

        snapshot_cost = _compute_inventory_cost(conn, snapshot_date)
        cashflow_cost = float(cashflow_row["inventory_cost_close"] or 0.0)
        diff = abs(snapshot_cost - cashflow_cost)
        allowed = max(tolerance_kzt, abs(snapshot_cost) * tolerance_pct)

        print(f"snapshot_date={snapshot_date}")
        print(f"snapshot_cost_kzt={snapshot_cost:,.2f}")
        print(f"cashflow_cost_kzt={cashflow_cost:,.2f}")
        print(f"diff_kzt={diff:,.2f}")
        print(f"allowed_kzt={allowed:,.2f}")

        if diff > allowed:
            print("FAIL: inventory cost drift exceeds tolerance")
            return 1

        print("PASS: inventory cost drift within tolerance")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate inventory cost drift vs snapshots")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--tolerance-pct", type=float, default=0.02)
    parser.add_argument("--tolerance-kzt", type=float, default=50000.0)
    args = parser.parse_args()
    return validate_drift(args.db, args.as_of, args.tolerance_pct, args.tolerance_kzt)


if __name__ == "__main__":
    raise SystemExit(main())
