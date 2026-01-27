#!/usr/bin/env python3
"""
Deprecated: use scripts/import_opex_protocol.py (CSV converted from OPEX_protocol_26.01.2026.xlsx).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _month_add(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, 28)  # keep safe
    return date(year, month, day)


def main() -> int:
    print("ERROR: generate_recurring_commitments is deprecated.")
    print("Use scripts/import_opex_protocol.py with a CSV converted via excel-safe-ops.")
    return 2

    parser = argparse.ArgumentParser(description="Generate recurring OPEX commitments")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-date", type=str, required=True)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--amount-kzt", type=float, required=True)
    parser.add_argument("--scenario-tag", type=str, default="base")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(f"DB not found: {args.db}")

    start = date.fromisoformat(args.start_date)
    entries = []
    for i in range(args.months):
        commit_date = _month_add(start, i)
        entries.append({
            "commit_date": commit_date.isoformat(),
            "commit_type": "OPEX",
            "amount_kzt": args.amount_kzt,
            "scenario_tag": args.scenario_tag,
            "ref_id": "OPEX_MONTHLY",
            "notes": "Monthly OPEX",
        })

    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_commitments"):
            raise RuntimeError("fact_cashflow_commitments missing; run migrate_018_cashflow_calendar.py")

        existing = set()
        for row in conn.execute(
            "SELECT commit_date, commit_type, amount_kzt, scenario_tag, ref_id FROM fact_cashflow_commitments"
        ):
            existing.add((row[0], row[1], float(row[2]), row[3], row[4]))

        new_rows = [r for r in entries if (r["commit_date"], r["commit_type"], float(r["amount_kzt"]), r["scenario_tag"], r["ref_id"]) not in existing]

        print(f"Generated commitments: {len(entries)}")
        print(f"New commitments: {len(new_rows)} (existing skipped: {len(entries) - len(new_rows)})")

        if args.apply:
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


if __name__ == "__main__":
    raise SystemExit(main())
