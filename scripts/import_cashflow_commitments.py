#!/usr/bin/env python3
"""
Import cashflow commitments from CSV into fact_cashflow_commitments.

Default: DRY RUN. Apply requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _normalize_amount(val: str | None) -> float:
    try:
        return float(str(val).replace(",", "").strip())
    except Exception:
        return 0.0


def import_commitments(csv_path: Path, db_path: Path, apply: bool, replace: bool) -> int:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_commitments"):
            raise RuntimeError("fact_cashflow_commitments missing; run migrate_018_cashflow_calendar.py")

        reader = csv.DictReader(csv_path.open("r", newline=""))
        required = {"commit_date", "amount_kzt", "commit_type"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV missing required columns: {required}")

        rows = [r for r in reader if not (r.get("commit_date", "").startswith("#"))]
        to_insert = []
        for row in rows:
            commit_date = (row.get("commit_date") or "").strip()
            commit_type = (row.get("commit_type") or "").strip().upper()
            amount = _normalize_amount(row.get("amount_kzt"))
            scenario_tag = (row.get("scenario_tag") or "base").strip()
            ref_id = (row.get("ref_id") or row.get("po_id") or "").strip() or None
            notes = (row.get("notes") or "").strip() or None
            if not commit_date or amount == 0 or not commit_type:
                continue
            to_insert.append({
                "commit_date": commit_date,
                "commit_type": commit_type,
                "amount_kzt": amount,
                "scenario_tag": scenario_tag,
                "ref_id": ref_id,
                "notes": notes,
            })

        existing = set()
        for row in conn.execute(
            "SELECT commit_date, commit_type, amount_kzt, scenario_tag, ref_id FROM fact_cashflow_commitments"
        ):
            existing.add((row[0], row[1], float(row[2]), row[3], row[4]))

        new_rows = [r for r in to_insert if (r["commit_date"], r["commit_type"], float(r["amount_kzt"]), r["scenario_tag"], r["ref_id"]) not in existing]

        print(f"Rows in CSV: {len(rows)}")
        print(f"New commitments: {len(new_rows)} (existing skipped: {len(to_insert) - len(new_rows)})")

        if apply:
            if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
                raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")
            if replace:
                refs = {(r["ref_id"], r["commit_type"]) for r in to_insert if r.get("ref_id")}
                for ref_id, commit_type in refs:
                    conn.execute(
                        "DELETE FROM fact_cashflow_commitments WHERE ref_id = ? AND commit_type = ?",
                        (ref_id, commit_type),
                    )
                if refs:
                    print(f"APPLY: replaced commitments for {len(refs)} ref_id(s).")
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
            print("APPLY: inserted commitments.")
        else:
            print("DRY RUN: no DB writes.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Import cashflow commitments from CSV")
    parser.add_argument("csv_path", type=Path, help="Path to commitments CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Replace existing commitments for same ref_id + type")
    args = parser.parse_args()

    return import_commitments(args.csv_path, args.db, args.apply, args.replace)


if __name__ == "__main__":
    raise SystemExit(main())
