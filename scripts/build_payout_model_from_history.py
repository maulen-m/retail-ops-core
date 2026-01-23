#!/usr/bin/env python3
"""
Build payout lag model from statement-backed history.

Uses PAYOUT_RECEIVED events (STATEMENT_ACTUAL) and sales accrual history
to infer lag distribution (median + p80).
"""

from __future__ import annotations

import argparse
import statistics
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.payout_model import PayoutModel, save_payout_model  # noqa: E402
from scripts.rebuild_cashflow_calendar import _build_sales_aggregates  # noqa: E402
from core.config.business_params import get_fx_rates  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _load_statement_payouts(
    conn: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> dict[str, float]:
    if not _table_exists(conn, "fact_cashflow_events"):
        return {}
    rows = conn.execute(
        """
        SELECT event_date, SUM(amount_kzt) as amount
        FROM fact_cashflow_events
        WHERE event_type = 'PAYOUT_RECEIVED'
          AND source = 'STATEMENT_ACTUAL'
          AND event_date BETWEEN ? AND ?
        GROUP BY event_date
        """,
        (start_date.isoformat(), end_date.isoformat()),
    ).fetchall()
    return {row[0]: float(row[1] or 0.0) for row in rows if row[0]}


def _infer_lags(
    payouts_by_date: dict[str, float],
    sales_by_date: dict[str, float],
    max_lag_days: int,
) -> list[int]:
    lags: list[int] = []
    for payout_date_str, payout_amount in payouts_by_date.items():
        if payout_amount <= 0:
            continue
        payout_date = date.fromisoformat(payout_date_str)
        best_lag = None
        best_delta = None
        for lag in range(1, max_lag_days + 1):
            sale_date = payout_date - timedelta(days=lag)
            sale_amount = sales_by_date.get(sale_date.isoformat(), 0.0)
            if sale_amount <= 0:
                continue
            delta = abs(sale_amount - payout_amount)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_lag = lag
        if best_lag is not None:
            lags.append(best_lag)
    return lags


def build_model(db_path: Path, start_date: str | None, end_date: str | None, max_lag_days: int) -> PayoutModel:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_events"):
            raise RuntimeError("fact_cashflow_events missing; run migrate_018_cashflow_calendar.py")

        if not start_date or not end_date:
            row = conn.execute(
                "SELECT MIN(event_date) as min_date, MAX(event_date) as max_date FROM fact_cashflow_events"
            ).fetchone()
            if not start_date:
                start_date = row["min_date"] if row and row["min_date"] else date.today().isoformat()
            if not end_date:
                end_date = row["max_date"] if row and row["max_date"] else date.today().isoformat()

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        fx_rates = get_fx_rates(end, db_path=db_path)
        sales_by_date, _ = _build_sales_aggregates(conn, start, end, fx_rates)
        payouts_by_date = _load_statement_payouts(conn, start, end)

    lags = _infer_lags(payouts_by_date, sales_by_date, max_lag_days)
    if not lags:
        return PayoutModel(base_lag_days=7, conservative_lag_days=10, sample_size=0, source="DEFAULT")

    median_lag = int(round(statistics.median(lags)))
    p80_index = max(0, int(round(len(lags) * 0.8)) - 1)
    p80_lag = sorted(lags)[p80_index] if lags else median_lag

    return PayoutModel(
        base_lag_days=median_lag,
        conservative_lag_days=max(median_lag, p80_lag),
        updated_at=datetime.now().isoformat(),
        sample_size=len(lags),
        source="STATEMENT_ACTUAL",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build payout lag model from statement history")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-date", type=str, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="End date YYYY-MM-DD")
    parser.add_argument("--max-lag-days", type=int, default=14)
    args = parser.parse_args()

    model = build_model(args.db, args.start_date, args.end_date, args.max_lag_days)
    save_payout_model(model)

    print("Payout model updated")
    print(f"  base_lag_days: {model.base_lag_days}")
    print(f"  conservative_lag_days: {model.conservative_lag_days}")
    print(f"  sample_size: {model.sample_size}")
    print(f"  source: {model.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
