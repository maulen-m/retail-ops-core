#!/usr/bin/env python3
"""
Validate cashflow daily roll-forward identities.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def validate(db_path: Path, tolerance: float) -> int:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_cashflow_daily"):
            print("FAIL: fact_cashflow_daily missing")
            return 1
        rows = conn.execute(
            "SELECT * FROM fact_cashflow_daily ORDER BY date"
        ).fetchall()
        if not rows:
            print("FAIL: fact_cashflow_daily is empty")
            return 1

        failures = 0
        for row in rows:
            cash_ok = abs((row["cash_open"] + row["cash_flow_kzt"]) - row["cash_close"]) <= tolerance
            recv_ok = abs((row["receivables_open"] + row["receivables_flow_kzt"]) - row["receivables_close"]) <= tolerance
            inv_ok = abs((row["inventory_cost_open"] + row["inventory_cost_flow_kzt"]) - row["inventory_cost_close"]) <= tolerance
            capital_ok = abs((row["cash_close"] + row["receivables_close"] + row["inventory_cost_close"]) - row["capital_close"]) <= tolerance

            if not (cash_ok and recv_ok and inv_ok and capital_ok):
                failures += 1
                print(f"FAIL {row['date']}: roll-forward mismatch")
            if row["cash_close"] < -tolerance:
                failures += 1
                print(f"FAIL {row['date']}: cash_close negative {row['cash_close']}")
            if row["receivables_close"] < -tolerance:
                failures += 1
                print(f"FAIL {row['date']}: receivables_close negative {row['receivables_close']}")
            for field in ("inventory_on_hand_close", "inventory_inbound_close", "inventory_on_delivery_close"):
                if field in row.keys() and row[field] is not None and row[field] < -tolerance:
                    failures += 1
                    print(f"FAIL {row['date']}: {field} negative {row[field]}")

        if failures:
            print(f"FAIL: {failures} invariant violations")
            return 1

        print(f"PASS: {len(rows)} days validated")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate cashflow calendar invariants")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--tolerance", type=float, default=0.01, help="Allowed numeric tolerance")
    args = parser.parse_args()
    return validate(args.db, args.tolerance)


if __name__ == "__main__":
    raise SystemExit(main())
