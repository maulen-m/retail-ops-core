#!/usr/bin/env python3
"""Workbook-anchored validator for published sales truth (read-only)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_sales_against_workbook import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    validate_sales_against_workbook,
)


def validate_sales_vs_workbook_anchor(
    *,
    db_path: Path,
    workbook_path: Path,
    sheet_name: str = DEFAULT_SHEET,
    days: int = 14,
    tol_pct: float = 5.0,
    as_of: str | None = None,
    min_overlap_days: int = 7,
    max_lag_days: int = 1,
) -> dict[str, Any]:
    return validate_sales_against_workbook(
        db_path=db_path,
        workbook_path=workbook_path,
        sheet_name=sheet_name,
        days=days,
        tol_pct=tol_pct,
        as_of=as_of,
        min_overlap_days=min_overlap_days,
        max_lag_days=max_lag_days,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate published sales truth vs workbook anchor")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", type=str, default=DEFAULT_SHEET)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--tol-pct", type=float, default=5.0)
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--min-overlap-days", type=int, default=7)
    parser.add_argument("--max-lag-days", type=int, default=1)
    args = parser.parse_args()

    report = validate_sales_vs_workbook_anchor(
        db_path=args.db,
        workbook_path=args.workbook,
        sheet_name=args.sheet,
        days=args.days,
        tol_pct=args.tol_pct,
        as_of=args.as_of,
        min_overlap_days=args.min_overlap_days,
        max_lag_days=args.max_lag_days,
    )
    print(
        "window="
        f"{report['window_start']}..{report['window_end']} "
        f"overlap_days={report['overlap_days']} ok={report['ok']}"
    )
    if report["errors"]:
        for err in report["errors"]:
            print(f"ERROR: {err}")
        return 1
    print("OK: published truth does not exceed workbook tolerance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
