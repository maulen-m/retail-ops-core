#!/usr/bin/env python3
"""
Generate a PO payment plan CSV from po_header totals.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config.business_params import get_fx_rates

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUT = PROJECT_ROOT / "data" / "cashflow" / "po_payment_plan.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PO payment plan CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--po-id", action="append", dest="po_ids", default=["PO-4.1", "PO-4.2", "PO-5"])
    parser.add_argument("--scenario-tag", type=str, default="base")
    parser.add_argument("--as-of", type=str, default="2026-01-22")
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(f"DB not found: {args.db}")

    fx = get_fx_rates(args.as_of, db_path=args.db)

    with sqlite3.connect(str(args.db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT po_id, supplier_code, message_date, ship_date_cargo, total_cost_cny
            FROM po_header
            WHERE po_id IN ({})
            """.format(",".join("?" * len(args.po_ids))),
            args.po_ids,
        ).fetchall()

    out_rows = []
    for row in rows:
        total_cny = float(row["total_cost_cny"] or 0.0)
        if total_cny <= 0:
            continue
        amount_kzt = round(total_cny * fx.cny_kzt, 2)
        commit_date = row["ship_date_cargo"] or row["message_date"] or args.as_of
        out_rows.append({
            "commit_date": commit_date,
            "amount_kzt": amount_kzt,
            "po_id": row["po_id"],
            "supplier": row["supplier_code"],
            "scenario_tag": args.scenario_tag,
            "notes": "Auto-generated from po_header total_cost_cny",
            "commit_type": "PO_PAYMENT",
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["commit_date", "amount_kzt", "po_id", "supplier", "scenario_tag", "notes", "commit_type"],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
