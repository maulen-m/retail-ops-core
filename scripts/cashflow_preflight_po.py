#!/usr/bin/env python3
"""
Cashflow preflight gate for PO affordability.

Default: evaluate base scenario for next 60 days using commitments + payout model.
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.payout_model import load_payout_model
from core.db.queries import get_cutoff_date_almaty
from scripts.update_cashflow_dashboard import _build_forecast_rows

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
EXPORT_PATH = PROJECT_ROOT / "exports" / "cashflow_preflight_report.txt"


@dataclass
class PreflightResult:
    ok: bool
    min_cash: float
    min_cash_date: str | None
    scenario: str
    horizon_days: int
    reason: str | None = None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _load_daily(conn: sqlite3.Connection, cutoff: date, history_days: int) -> list[dict]:
    if not _table_exists(conn, "fact_cashflow_daily"):
        return []
    start = cutoff - timedelta(days=history_days - 1)
    rows = conn.execute(
        "SELECT * FROM fact_cashflow_daily WHERE date BETWEEN ? AND ? ORDER BY date",
        (start.isoformat(), cutoff.isoformat()),
    ).fetchall()
    return [dict(r) for r in rows]


def _load_commitments(conn: sqlite3.Connection, start: date, end: date) -> list:
    if not _table_exists(conn, "fact_cashflow_commitments"):
        return []
    rows = conn.execute(
        """
        SELECT commit_date, commit_type, amount_kzt, scenario_tag, ref_id, notes
        FROM fact_cashflow_commitments
        WHERE commit_date BETWEEN ? AND ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return [
        {
            "commit_date": r[0],
            "commit_type": r[1],
            "amount_kzt": float(r[2] or 0.0),
            "scenario_tag": r[3],
            "ref_id": r[4],
            "notes": r[5],
        }
        for r in rows
    ]


def _min_cash(rows: list[dict]) -> dict:
    if not rows:
        return {"date": None, "cash_close": 0}
    return min(rows, key=lambda r: r.get("cash_close", 0) or 0)


def evaluate_preflight(db_path: Path, horizon_days: int, scenario: str, min_cash_threshold: float) -> PreflightResult:
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    cutoff = get_cutoff_date_almaty()
    payout_model = load_payout_model()
    payout_lag = payout_model.base_lag_days
    if scenario == "conservative":
        payout_lag = max(payout_model.conservative_lag_days, payout_lag)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        history = _load_daily(conn, cutoff, history_days=90)
        if not history:
            return PreflightResult(
                ok=False,
                min_cash=0.0,
                min_cash_date=None,
                scenario=scenario,
                horizon_days=horizon_days,
                reason="fact_cashflow_daily is empty",
            )

        last_date = date.fromisoformat(history[-1]["date"])
        forecast_start = last_date + timedelta(days=1)
        forecast_end = forecast_start + timedelta(days=horizon_days - 1)
        commitments = _load_commitments(conn, forecast_start, forecast_end)
        forecast_rows = _build_forecast_rows(history, commitments, horizon_days, payout_lag, "preflight")
        all_rows = history + forecast_rows

    min_row = _min_cash(all_rows)
    min_cash = float(min_row.get("cash_close") or 0.0)
    ok = min_cash >= min_cash_threshold
    reason = None if ok else f"min_cash {min_cash:.2f} below threshold {min_cash_threshold:.2f}"

    return PreflightResult(
        ok=ok,
        min_cash=min_cash,
        min_cash_date=min_row.get("date"),
        scenario=scenario,
        horizon_days=horizon_days,
        reason=reason,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Cashflow preflight for PO affordability")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite DB")
    parser.add_argument("--days", type=int, default=60, help="Forecast horizon days")
    parser.add_argument("--scenario", choices=["base", "conservative"], default="base")
    parser.add_argument("--min-cash", type=float, default=0.0, help="Minimum acceptable cash close")
    parser.add_argument("--override", action="store_true", help="Allow failure with explicit reason")
    parser.add_argument("--reason", type=str, default=None, help="Override reason for failing preflight")
    args = parser.parse_args()

    result = evaluate_preflight(args.db, args.days, args.scenario, args.min_cash)

    lines = [
        f"scenario: {result.scenario}",
        f"horizon_days: {result.horizon_days}",
        f"min_cash_kzt: {result.min_cash:.2f}",
        f"min_cash_date: {result.min_cash_date}",
        f"status: {'PASS' if result.ok else 'FAIL'}",
    ]

    if not result.ok:
        lines.append(f"reason: {result.reason}")
        if args.override:
            if not args.reason:
                print("FAIL: override requires --reason")
                return 2
            lines.append(f"override: {args.reason}")
        else:
            EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            EXPORT_PATH.write_text("\n".join(lines) + "\n")
            print("\n".join(lines))
            return 1

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
