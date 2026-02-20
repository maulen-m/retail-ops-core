#!/usr/bin/env python3
"""
Reconcile cashflow calendar to a known cash balance at a given date.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rebuild_cashflow_calendar import compute_daily_rows, _fetch_manual_events, _build_system_events, _resolve_start_end
from core.config.business_params import get_fx_rates

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
EXPORT_DIR = PROJECT_ROOT / "exports"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile cashflow to known cash")
    parser.add_argument("--as-of", required=True, help="As-of date YYYY-MM-DD")
    parser.add_argument("--known-cash-kzt", required=True, type=float)
    parser.add_argument("--tolerance", type=float, default=1.0)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)

    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")
        start, _ = _resolve_start_end(conn)
        end = as_of
        fx_rates = get_fx_rates(end, db_path=args.db)
        manual = _fetch_manual_events(conn, start, end)
        system = _build_system_events(conn, start, end, fx_rates, run_id=datetime.now().strftime("%Y%m%d_%H%M%S"))
        rows = compute_daily_rows(manual + system, start, end, run_id="reconcile")

        cash_row = next((r for r in rows if r["date"] == args.as_of), None)
        if not cash_row:
            raise RuntimeError(f"No cashflow row for {args.as_of}")
        cash_close = float(cash_row["cash_close"])
        diff = cash_close - float(args.known_cash_kzt)

        adjustment_exists = False
        for row in conn.execute(
            """
            SELECT COUNT(*) as cnt FROM fact_cashflow_events
            WHERE event_type = 'ADJUSTMENT' AND account = 'CASH' AND event_date <= ?
            """,
            (args.as_of,),
        ):
            adjustment_exists = row[0] > 0

    report_lines = [
        f"Cashflow reconciliation for {args.as_of}",
        f"Known cash: {args.known_cash_kzt:,.2f} KZT",
        f"Computed cash_close: {cash_close:,.2f} KZT",
        f"Diff (computed - known): {diff:,.2f} KZT",
        f"Adjustment event exists: {'YES' if adjustment_exists else 'NO'}",
    ]

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EXPORT_DIR / f"cashflow_reconciliation_{args.as_of.replace('-', '')}.md"
    report_path.write_text("\n".join(report_lines) + "\n")
    print(f"Reconciliation report: {report_path}")

    if abs(diff) > args.tolerance and not adjustment_exists:
        print("FAIL: cash mismatch exceeds tolerance and no adjustment event present")
        return 1

    print("PASS: cash reconciliation within tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
