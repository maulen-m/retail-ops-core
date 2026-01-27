#!/usr/bin/env python3
"""
Import OPEX commitments from a protocol CSV (converted from the XLSX protocol).

Note: Conversion from XLSX must be done via excel-safe-ops (control plane).
Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _read_rows(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()})
    return rows


def _coerce_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(" ", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = value.day
    # clamp to last day of month
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def _safe_day_in_month(base: date, day_of_month: int) -> date:
    day = max(1, day_of_month)
    while True:
        try:
            return date(base.year, base.month, day)
        except ValueError:
            day -= 1


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _month_starts(start: date, end: date) -> Iterable[date]:
    current = date(start.year, start.month, 1)
    while current <= end:
        yield current
        current = _add_months(current, 1)


def _parse_protocol_xlsx(xlsx_path: Path, horizon_days: int) -> list[dict]:
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("pandas is required to parse OPEX protocol XLSX") from exc

    df = pd.read_excel(xlsx_path)
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        raise RuntimeError("OPEX protocol XLSX has no rows")

    today_col = next((c for c in df.columns if c.lower() == "today_date"), None)
    start_date = date.today()
    if today_col:
        for raw in df[today_col].tolist():
            if pd.notna(raw):
                try:
                    start_date = pd.to_datetime(raw).date()
                    break
                except Exception:
                    continue

    end_date = start_date + timedelta(days=horizon_days - 1)
    entries: list[dict] = []

    for idx, row in df.iterrows():
        schedule = str(row.get("payment_schedule", "")).strip().lower()
        if schedule not in {"daily", "monthly"}:
            continue

        amount_monthly = _coerce_float(row.get("amount_monthly_kzt"))
        amount_daily = _coerce_float(row.get("amount_daily_kzt"))
        if schedule == "daily":
            amount = amount_daily or (amount_monthly / 30.0 if amount_monthly else 0.0)
            if amount <= 0:
                continue
        else:
            if amount_monthly <= 0:
                continue

        months_left = _coerce_int(row.get("Months_of_payments_left_estimate"))
        row_end = end_date
        if months_left and months_left > 0:
            row_end = min(end_date, _add_months(start_date, months_left) - timedelta(days=1))

        expense_type = str(row.get("Expense_type", "")).strip()
        expense_name = str(row.get("Expense_name", "")).strip()
        notes = f"{expense_type}: {expense_name}".strip(": ").strip()

        ref_id = f"OPEX_PROTOCOL_{idx + 1:02d}"

        if schedule == "daily":
            for day in _date_range(start_date, row_end):
                entries.append(
                    {
                        "commit_date": day.isoformat(),
                        "commit_type": "OPEX",
                        "amount_kzt": round(amount, 2),
                        "scenario_tag": "base",
                        "ref_id": ref_id,
                        "notes": notes or "OPEX protocol import (daily)",
                    }
                )
        else:
            day_of_month = _coerce_int(row.get("Day_of_the_mnth"))
            if not day_of_month:
                continue
            for month_start in _month_starts(start_date, row_end):
                commit_date = _safe_day_in_month(month_start, day_of_month)
                if commit_date < start_date or commit_date > row_end:
                    continue
                entries.append(
                    {
                        "commit_date": commit_date.isoformat(),
                        "commit_type": "OPEX",
                        "amount_kzt": round(amount_monthly, 2),
                        "scenario_tag": "base",
                        "ref_id": ref_id,
                        "notes": notes or "OPEX protocol import (monthly)",
                    }
                )

    if not entries:
        raise RuntimeError("No commitments generated from OPEX protocol XLSX")
    return entries


def _entries_from_csv(rows: list[dict]) -> list[dict]:
    required = {"commit_date", "amount_kzt"}
    missing = required - set(rows[0].keys())
    if missing:
        raise RuntimeError(f"Missing required columns: {sorted(missing)}")

    entries = []
    for row in rows:
        commit_date = row.get("commit_date")
        if not commit_date:
            continue
        amount = float((row.get("amount_kzt") or "0").replace(" ", ""))
        if amount == 0:
            continue
        entries.append(
            {
                "commit_date": commit_date,
                "commit_type": row.get("commit_type") or "OPEX",
                "amount_kzt": amount,
                "scenario_tag": row.get("scenario_tag") or "base",
                "ref_id": row.get("ref_id") or "OPEX_PROTOCOL",
                "notes": row.get("notes") or "OPEX protocol import",
            }
        )
    return entries


def import_opex(
    csv_path: Path | None,
    xlsx_path: Path | None,
    db_path: Path,
    apply: bool,
    horizon_days: int,
    replace_existing: bool,
) -> int:
    if csv_path is None and xlsx_path is None:
        raise ValueError("Provide --csv or --xlsx")
    if csv_path and not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if xlsx_path and not xlsx_path.exists():
        raise FileNotFoundError(f"XLSX not found: {xlsx_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    if xlsx_path:
        entries = _parse_protocol_xlsx(xlsx_path, horizon_days)
    else:
        rows = _read_rows(csv_path)
        if not rows:
            raise RuntimeError("No rows found in CSV")
        entries = _entries_from_csv(rows)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_commitments"):
            raise RuntimeError("fact_cashflow_commitments missing; run migrate_018_cashflow_calendar.py")

        if apply and replace_existing:
            conn.execute("DELETE FROM fact_cashflow_commitments WHERE commit_type = 'OPEX'")
            conn.commit()

        existing = {
            (row[0], row[1], float(row[2]), row[3], row[4])
            for row in conn.execute(
                "SELECT commit_date, commit_type, amount_kzt, scenario_tag, ref_id FROM fact_cashflow_commitments"
            )
        }

        new_rows = [
            r
            for r in entries
            if (r["commit_date"], r["commit_type"], float(r["amount_kzt"]), r["scenario_tag"], r["ref_id"]) not in existing
        ]

        print(f"Commitments parsed: {len(entries)}")
        print(f"New commitments: {len(new_rows)} (existing skipped: {len(entries) - len(new_rows)})")
        if apply and replace_existing:
            print("APPLY: replaced existing OPEX commitments.")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            for r in new_rows:
                conn.execute(
                    """
                    INSERT INTO fact_cashflow_commitments (
                        commit_date, commit_type, amount_kzt, probability, scenario_tag, ref_id, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["commit_date"],
                        r["commit_type"],
                        r["amount_kzt"],
                        None,
                        r["scenario_tag"],
                        r["ref_id"],
                        r["notes"],
                    ),
                )
            conn.commit()
            print("APPLY: inserted OPEX commitments.")
        else:
            print("DRY RUN: no DB writes.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import OPEX commitments from protocol CSV")
    parser.add_argument("--csv", type=Path, help="CSV converted from OPEX protocol XLSX")
    parser.add_argument("--xlsx", type=Path, help="OPEX protocol XLSX (read-only)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--horizon-days", type=int, default=365)
    parser.add_argument("--replace-existing", action="store_true", help="Replace existing OPEX commitments")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return import_opex(args.csv, args.xlsx, args.db, args.apply, args.horizon_days, args.replace_existing)


if __name__ == "__main__":
    raise SystemExit(main())
