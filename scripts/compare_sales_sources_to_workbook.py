#!/usr/bin/env python3
"""Read-only comparison of workbook sales totals vs DB sales sources."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_sales_against_workbook import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    load_daily_source,
    parse_workbook_daily_totals,
)


def _fmt_num(value: float) -> str:
    return f"{value:,.2f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [sep, fmt_row(headers), sep]
    out.extend(fmt_row(r) for r in rows)
    out.append(sep)
    return "\n".join(out)


def compare_sales_sources_to_workbook(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date > end_date:
        raise ValueError("start date must be <= end date")

    workbook_daily = parse_workbook_daily_totals(workbook_path, sheet_name=sheet_name)
    conn = sqlite3.connect(str(db_path))
    try:
        v2_daily = load_daily_source(conn, "sales_fact_v2")
        fs_daily = load_daily_source(conn, "fact_sales")
        published_daily = load_daily_source(conn, "published_truth")
    finally:
        conn.close()

    rows: list[dict[str, Any]] = []
    day = start_date
    while day <= end_date:
        key = day.isoformat()
        wb = workbook_daily.get(key, {"units": 0.0, "net_rev_kzt": 0.0})
        v2 = v2_daily.get(key, {"units": 0.0, "net_rev_kzt": 0.0})
        fs = fs_daily.get(key, {"units": 0.0, "net_rev_kzt": 0.0})
        pub = published_daily.get(key, {"units": 0.0, "net_rev_kzt": 0.0})
        rows.append(
            {
                "date": key,
                "workbook_units": float(wb["units"]),
                "workbook_net_rev_kzt": float(wb["net_rev_kzt"]),
                "v2_units": float(v2["units"]),
                "v2_net_rev_kzt": float(v2["net_rev_kzt"]),
                "fact_sales_units": float(fs["units"]),
                "fact_sales_net_rev_kzt": float(fs["net_rev_kzt"]),
                "published_units": float(pub["units"]),
                "published_net_rev_kzt": float(pub["net_rev_kzt"]),
            }
        )
        day += timedelta(days=1)
    return {"rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare workbook sales totals to DB sources")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--start", type=str, required=True)
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--output-csv", type=Path, default=None)
    args = parser.parse_args()

    report = compare_sales_sources_to_workbook(
        db_path=args.db,
        workbook_path=args.workbook,
        sheet_name=args.sheet,
        start=args.start,
        end=args.end,
    )

    print(
        _table(
            [
                "date",
                "wb_units",
                "wb_net",
                "v2_units",
                "v2_net",
                "fs_units",
                "fs_net",
                "pub_units",
                "pub_net",
            ],
            [
                [
                    r["date"],
                    _fmt_num(r["workbook_units"]),
                    _fmt_num(r["workbook_net_rev_kzt"]),
                    _fmt_num(r["v2_units"]),
                    _fmt_num(r["v2_net_rev_kzt"]),
                    _fmt_num(r["fact_sales_units"]),
                    _fmt_num(r["fact_sales_net_rev_kzt"]),
                    _fmt_num(r["published_units"]),
                    _fmt_num(r["published_net_rev_kzt"]),
                ]
                for r in report["rows"]
            ],
        )
    )

    if args.output_csv is not None:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "date",
                    "workbook_units",
                    "workbook_net_rev_kzt",
                    "v2_units",
                    "v2_net_rev_kzt",
                    "fact_sales_units",
                    "fact_sales_net_rev_kzt",
                    "published_units",
                    "published_net_rev_kzt",
                ],
            )
            writer.writeheader()
            writer.writerows(report["rows"])
        print(f"csv_path={args.output_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
